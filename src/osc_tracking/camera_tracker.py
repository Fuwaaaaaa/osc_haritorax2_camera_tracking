"""Dual camera tracker using MediaPipe Pose Landmarker + stereo triangulation.

Runs MediaPipe inference in a subprocess to bypass the Python GIL.
Camera frames are captured in the subprocess, landmarks are extracted,
and 3D positions are computed via stereo triangulation.

Architecture (2-process model):
    ┌─────────────────────────────────┐
    │        Camera Subprocess         │
    │  ┌──────────┐  ┌──────────┐    │
    │  │ Camera 1  │  │ Camera 2  │   │
    │  │ MediaPipe │  │ MediaPipe │   │
    │  └─────┬─────┘  └─────┬─────┘  │
    │        └──────┬───────┘         │
    │          Triangulate            │
    │               │                 │
    └───────────────┼─────────────────┘
                    │ shared_memory
                    ▼
    ┌─────────────────────────────────┐
    │         Main Process             │
    │  (Fusion Engine reads results)   │
    └─────────────────────────────────┘
"""

import itertools
import logging
import multiprocessing as mp
import time
from dataclasses import dataclass
from multiprocessing import shared_memory
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# 9 joints x (3 position + 2 per-camera vis + 1 combined + 1 timestamp) = 63 floats
JOINT_COUNT = 9
FLOATS_PER_JOINT = 7  # x, y, z, cam1_vis, cam2_vis, combined_conf, timestamp
SHM_SIZE = JOINT_COUNT * FLOATS_PER_JOINT * 8  # float64 = 8 bytes
SHM_LAYOUT_VERSION = 2  # Bump when FLOATS_PER_JOINT changes
SHM_NAME = f"osc_tracking_camera_v{SHM_LAYOUT_VERSION}"

# MediaPipe Pose Landmarker index → our joint name mapping
# https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker
LANDMARK_TO_JOINT = {
    0: "Head",           # nose (proxy for head)
    11: "Chest",         # left shoulder (proxy for chest center)
    12: "RightShoulder", # used by Visual Compass
    23: "Hips",          # left hip (proxy for hips center, averaged with right)
    24: "HipsR",         # right hip (averaged with left for center)
    25: "LeftKnee",
    26: "RightKnee",
    27: "LeftFoot",
    28: "RightFoot",
    13: "LeftElbow",
    14: "RightElbow",
}

# Indices we actually need from MediaPipe (33 total landmarks available)
NEEDED_LANDMARKS = [0, 11, 12, 13, 14, 23, 24, 25, 26, 27, 28]

MODEL_PATH_DEFAULT = "models/pose_landmarker_heavy.task"
MODEL_PATH_LITE = "models/pose_landmarker_lite.task"


def _next_monotonic_ms(prev_ms: int) -> int:
    """Return a strictly-increasing millisecond timestamp for MediaPipe VIDEO mode.

    MediaPipe rejects non-monotonic frame timestamps. Using wall-clock time
    tracks frame drops accurately (the previous ``prev_ms += 1000 / fps``
    pattern lied to MP when FPS dipped). If two frames resolve to the same
    millisecond we force a +1 bump.
    """
    now_ms = int(time.monotonic() * 1000.0)
    if now_ms <= prev_ms:
        return prev_ms + 1
    return now_ms


# Thread-safe counter so back-to-back SHM allocations (e.g. across tests
# that instantiate multiple CameraTrackers) never collide on the same
# name. ``itertools.count`` is implemented in C and its ``__next__`` call
# is atomic under the GIL — no external lock needed.
_shm_name_counter = itertools.count(1)


def _zero_joint(buf: np.ndarray, i: int, now: float) -> None:
    """Write the "no data this frame" marker for one joint slot.

    Centralises the per-slot layout so a change to FLOATS_PER_JOINT
    doesn't require updating a dozen inline literals. The timestamp is
    still recorded so downstream staleness checks see the slot was
    touched this cycle, just with zero confidence.
    """
    buf[i] = [0.0] * (FLOATS_PER_JOINT - 1) + [now]


def _zero_all_joints(buf: np.ndarray, now: float) -> None:
    """Mark every joint as unobserved for this frame."""
    for i in range(JOINT_COUNT):
        _zero_joint(buf, i, now)


def _unique_shm_name() -> str:
    """Return a fresh shared-memory name that won't collide with a leaked
    SHM from a previously crashed instance. The PID-only scheme used before
    re-bound to stale buffers after a hard exit; a process-local counter
    ensures back-to-back calls also differ (``time.monotonic_ns`` resolution
    is low enough on Windows that consecutive calls can tie)."""
    return (
        f"{SHM_NAME}_{mp.current_process().pid}"
        f"_{time.monotonic_ns()}_{next(_shm_name_counter)}"
    )


@dataclass
class CameraConfig:
    """Configuration for the camera setup.

    ``cam_indices`` is the primary knob. 1 entry → monocular (MediaPipe
    z-depth fallback). 2 entries → stereo triangulation. 3+ entries →
    multi-view SVD-DLT triangulation (needs a multi-view calibration
    file; a 2-camera stereo file is promoted on load but does not
    benefit extra cameras).

    Legacy ``cam1_index`` / ``cam2_index`` stay for back-compat.
    """
    cam1_index: int = 0
    cam2_index: int = 1
    cam_indices: list[int] | None = None
    resolution: tuple[int, int] = (640, 480)
    target_fps: int = 30
    calibration_file: str = "calibration_data/stereo_calib.npz"
    model_path: str = MODEL_PATH_DEFAULT
    model_path_lite: str = MODEL_PATH_LITE
    # Bundle-adjustment refinement on top of linear DLT triangulation.
    # Default on for 3+ camera rigs (where the redundancy pays back the
    # optimisation cost) and off for 2 cameras (DLT is already optimal
    # there — refinement would only add ms of CPU for no accuracy win).
    refine_triangulation: bool | None = None

    def __post_init__(self) -> None:
        if self.cam_indices is None:
            self.cam_indices = [self.cam1_index, self.cam2_index]
        if not self.cam_indices:
            raise ValueError("cam_indices must contain at least one camera index")
        # Keep legacy fields consistent so back-compat callers still see
        # the first two cameras at the historical attribute names.
        self.cam1_index = self.cam_indices[0]
        # Mono mode: reuse cam1 for cam2 so the legacy 2-cam fallback path
        # stays valid on the degenerate case.
        self.cam2_index = self.cam_indices[1] if len(self.cam_indices) >= 2 else self.cam_indices[0]

    @property
    def effective_cam_indices(self) -> list[int]:
        """Every camera index the worker will open."""
        assert self.cam_indices is not None  # set in __post_init__
        return list(self.cam_indices)

    @property
    def camera_count(self) -> int:
        return len(self.effective_cam_indices)

    @property
    def effective_refine_triangulation(self) -> bool:
        """Resolve the tri-state ``refine_triangulation`` to a bool.

        ``None`` → auto: on iff there are 3+ cameras. Explicit True/False
        overrides auto, which lets a user force refinement on a 2-camera
        rig for testing or disable it on a 3-camera rig under tight
        latency budgets.
        """
        if self.refine_triangulation is not None:
            return self.refine_triangulation
        return self.camera_count >= 3


class CameraTracker:
    """Manages camera subprocess and reads triangulated results via shared memory."""

    def __init__(self, config: CameraConfig | None = None):
        self.config = config or CameraConfig()
        self._process: mp.Process | None = None
        self._shm: shared_memory.SharedMemory | None = None
        self._running = mp.Event()
        self._shm_lock = mp.Lock()

    def start(self) -> None:
        """Start the camera subprocess."""
        if self._process and self._process.is_alive():
            return

        # Retry with a fresh name on the unlikely event of collision.
        # Never reuse an existing SHM (create=False) — on a POSIX crash it
        # can hold stale joint data; on Windows the size may not even match.
        last_err: FileExistsError | None = None
        self._shm = None
        for _ in range(8):
            candidate = _unique_shm_name()
            try:
                self._shm = shared_memory.SharedMemory(
                    name=candidate, create=True, size=SHM_SIZE
                )
                self._shm_name = candidate
                break
            except FileExistsError as e:
                last_err = e
                logger.warning("SHM name %s already in use, retrying", candidate)
                continue
        if self._shm is None:
            raise RuntimeError(
                "Could not allocate a unique shared-memory name"
            ) from last_err

        self._running.set()
        self._process = mp.Process(
            target=_camera_worker,
            args=(self.config, self._shm_name, self._running, self._shm_lock),
            daemon=True,
            name="camera-tracker",
        )
        self._process.start()

    def stop(self) -> None:
        """Stop the camera subprocess."""
        self._running.clear()
        if self._process:
            self._process.join(timeout=3.0)
            if self._process.is_alive():
                self._process.terminate()
            self._process = None
        if self._shm:
            try:
                self._shm.close()
                self._shm.unlink()
            except FileNotFoundError:
                pass
            self._shm = None

    def read_joints(
        self,
    ) -> dict[str, tuple[np.ndarray, float, float, float]] | None:
        """Read latest joint data from shared memory.

        Returns:
            Dict mapping joint name to
            (position_xyz, combined_confidence, cam1_confidence, cam2_confidence),
            or None if shared memory is unavailable.
        """
        if self._shm is None:
            return None

        try:
            buf: np.ndarray = np.ndarray(
                (JOINT_COUNT, FLOATS_PER_JOINT),
                dtype=np.float64,
                buffer=self._shm.buf,
            )
        except (ValueError, BufferError):
            logger.warning("Shared memory read failed")
            return None

        from .complementary_filter import JOINT_NAMES

        with self._shm_lock:
            snapshot = buf.copy()

        results = {}
        now = time.monotonic()
        for i, name in enumerate(JOINT_NAMES):
            if i >= JOINT_COUNT:
                break
            x, y, z, cam1_vis, cam2_vis, conf, ts = snapshot[i]
            if not (np.isfinite(x) and np.isfinite(y) and np.isfinite(z)):
                continue
            if (now - ts) > 0.5:
                continue
            results[name] = (
                np.array([x, y, z]),
                float(conf),
                float(cam1_vis),
                float(cam2_vis),
            )

        return results

    @property
    def is_alive(self) -> bool:
        return self._process is not None and self._process.is_alive()


def _resolve_model_path(primary: str, fallback: str) -> Path | None:
    """Return the MediaPipe model path if it resolves inside the project.

    Config-supplied paths come from a JSON file on disk which the user
    may or may not audit. Containing the model to the project tree
    prevents a config smuggle like ``"model_path": "/etc/shadow"`` from
    handing MediaPipe an arbitrary file descriptor, and forces a caller
    who needs an out-of-tree model to do it explicitly (not via config).

    Returns ``None`` when neither path exists or both escape the project
    root — the caller then logs an instructive error instead of feeding
    a hostile path into the native library.
    """
    project_root = Path(__file__).resolve().parent.parent.parent

    def _safe_within_root(candidate: str) -> Path | None:
        if not candidate:
            return None
        try:
            resolved = Path(candidate).resolve()
        except OSError:
            return None
        if not resolved.exists():
            return None
        try:
            resolved.relative_to(project_root)
        except ValueError:
            logger.warning(
                "MediaPipe model path %s resolves outside the project root "
                "(%s); refusing to load.", resolved, project_root,
            )
            return None
        return resolved

    return _safe_within_root(primary) or _safe_within_root(fallback)


def _load_multiview_or_stereo(calibration_file: str):
    """Load calibration as MultiViewCalibration, promoting stereo if needed.

    Preference order:
      1. multi-view .npz at ``calibration_file`` (written by the new
         multi-view calibration flow)
      2. legacy stereo .npz at the same path, promoted via
         :func:`multiview_from_stereo` so triangulate_multiview can
         still run the 2-camera case

    Returns ``None`` when neither shape loads — the worker falls back
    to monocular depth estimation.
    """
    from .stereo_calibration import (
        load_calibration,
        load_multiview_calibration,
        multiview_from_stereo,
    )

    mv = load_multiview_calibration(calibration_file)
    if mv is not None:
        return mv
    stereo = load_calibration(calibration_file)
    if stereo is not None:
        return multiview_from_stereo(stereo)
    return None


def _init_pose_landmarkers(config: CameraConfig, count: int) -> list:
    """Build one MediaPipe PoseLandmarker per camera.

    MediaPipe's VIDEO-mode detector is stateful per call, so cameras
    must not share an instance. Returns an empty list on any init
    failure; callers treat that as "no pose data available" rather
    than aborting the worker.
    """
    try:
        import mediapipe as mp_lib  # noqa: F401
        from mediapipe.tasks.python import BaseOptions, vision
    except Exception as exc:
        logging.error("MediaPipe init failed (import): %s", exc)
        return []

    model_path = _resolve_model_path(config.model_path, config.model_path_lite)
    if model_path is None:
        logging.error(
            "MediaPipe model not found or outside the project tree. "
            "Download from: "
            "https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker#models "
            "and place at %s",
            config.model_path,
        )
        return []

    try:
        options = vision.PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        instances = [
            vision.PoseLandmarker.create_from_options(options)
            for _ in range(count)
        ]
    except Exception as exc:
        logging.error("MediaPipe init failed (instantiate): %s", exc)
        return []

    logging.info(
        "MediaPipe Pose Landmarker loaded: %s (%d instances)",
        model_path, len(instances),
    )
    return instances


def _camera_worker(
    config: CameraConfig,
    shm_name: str,
    running: "mp.synchronize.Event",  # type: ignore[name-defined]
    shm_lock: "mp.synchronize.Lock",  # type: ignore[name-defined]
) -> None:
    """Camera subprocess entry point.

    Captures frames from every camera in ``config.effective_cam_indices``,
    runs one MediaPipe Pose Landmarker instance per camera, and
    triangulates joints via SVD-DLT when ≥ 2 cameras + calibration are
    available. Falls back to monocular z-depth when a single camera
    or no calibration is present.
    """
    import cv2

    try:
        shm = shared_memory.SharedMemory(name=shm_name, create=False)
    except FileNotFoundError:
        return

    buf: np.ndarray = np.ndarray(
        (JOINT_COUNT, FLOATS_PER_JOINT),
        dtype=np.float64,
        buffer=shm.buf,
    )

    cam_indices = list(config.effective_cam_indices)

    def _open_all() -> list:
        opened = []
        for idx in cam_indices:
            cap = cv2.VideoCapture(idx)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.resolution[0])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.resolution[1])
            opened.append(cap)
        return opened

    caps = _open_all()

    frame_delay = 1.0 / config.target_fps

    mv_calib = _load_multiview_or_stereo(config.calibration_file)
    if mv_calib is None:
        logging.warning(
            "No stereo calibration found at %s. "
            "Run 'python -m osc_tracking.tools.calibrate' first. "
            "Falling back to monocular depth estimation.",
            config.calibration_file,
        )
    elif mv_calib.camera_count != len(cam_indices):
        logging.warning(
            "Calibration has %d cameras but config requests %d. "
            "Triangulation will use the min of the two. If you recently "
            "added/removed a camera, re-run the calibration tool.",
            mv_calib.camera_count,
            len(cam_indices),
        )

    pose_instances = _init_pose_landmarkers(config, len(cam_indices))

    consecutive_failures = 0
    frame_ts_ms = 0  # MediaPipe VIDEO mode needs monotonic timestamp in ms

    while running.is_set():
        loop_start = time.monotonic()

        reads = [cap.read() for cap in caps]
        if not all(ok for ok, _ in reads):
            consecutive_failures += 1
            if consecutive_failures >= 3:
                logging.error("Camera capture failed 3x — restarting all cameras")
                for cap in caps:
                    cap.release()
                time.sleep(1.0)
                caps = _open_all()
                consecutive_failures = 0
            continue

        frames = [frame for _, frame in reads]
        consecutive_failures = 0
        now = time.monotonic()
        frame_ts_ms = _next_monotonic_ms(frame_ts_ms)

        if pose_instances and len(pose_instances) == len(caps):
            try:
                import mediapipe as mp_lib

                landmark_sets: list = []
                for frame, pose in zip(frames, pose_instances):
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    mp_image = mp_lib.Image(
                        image_format=mp_lib.ImageFormat.SRGB, data=rgb
                    )
                    result = pose.detect_for_video(mp_image, frame_ts_ms)
                    landmark_sets.append(
                        result.pose_landmarks[0] if result.pose_landmarks else None
                    )

                if any(lms is not None for lms in landmark_sets):
                    with shm_lock:
                        _process_landmarks(
                            buf, landmark_sets, mv_calib, config.resolution, now,
                            refine=config.effective_refine_triangulation,
                        )
                else:
                    with shm_lock:
                        _zero_all_joints(buf, now)

            except Exception as e:
                logging.warning("MediaPipe inference failed: %s", e)
                with shm_lock:
                    _zero_all_joints(buf, now)
        else:
            with shm_lock:
                _zero_all_joints(buf, now)

        # Frame rate control
        elapsed = time.monotonic() - loop_start
        sleep_time = frame_delay - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    for cap in caps:
        cap.release()
    for pose in pose_instances:
        try:
            pose.close()
        except Exception:
            pass
    shm.close()


# MediaPipe landmark index pairs for each skeleton joint. ``None`` for the
# second index means "single landmark" (no averaging).
_MP_INDICES: dict[str, tuple[int, int | None]] = {
    "Hips": (23, 24),       # average of left+right hip
    "Chest": (11, 12),      # average of left+right shoulder
    "Head": (0, None),      # nose only
    "LeftFoot": (27, None),
    "RightFoot": (28, None),
    "LeftKnee": (25, None),
    "RightKnee": (26, None),
    "LeftElbow": (13, None),
    "RightElbow": (14, None),
}


def _landmark_pixel_and_vis(
    landmarks,
    idx_a: int,
    idx_b: int | None,
    w: int,
    h: int,
) -> tuple[np.ndarray, float]:
    """Resolve a skeleton joint to a pixel position + visibility.

    Returns ``(NaN-array, 0.0)`` when ``landmarks`` is missing so the
    triangulator treats this view as absent for that joint rather than
    pulling the estimate toward an imaginary pixel.
    """
    if landmarks is None:
        return np.array([np.nan, np.nan]), 0.0
    lm_a = landmarks[idx_a]
    vis = lm_a.visibility if hasattr(lm_a, "visibility") else 0.5
    px = np.array([lm_a.x * w, lm_a.y * h])
    if idx_b is not None:
        lm_b = landmarks[idx_b]
        vis_b = lm_b.visibility if hasattr(lm_b, "visibility") else 0.5
        px = (px + np.array([lm_b.x * w, lm_b.y * h])) / 2
        vis = (vis + vis_b) / 2
    return px, float(vis)


def _summarize_visibility_halves(per_view_vis: list[float]) -> tuple[float, float]:
    """Collapse per-camera visibility into the 2-slot layout the SHM uses.

    The on-wire layout still exposes exactly two per-camera confidences
    (``cam1_vis`` / ``cam2_vis``) because the state machine only has two
    degradation tiers (SINGLE_CAM_DEGRADED vs full). With N>2 cameras we
    split them in halves and report the min of each — this keeps the
    FusionEngine's asymmetric-loss detection meaningful without a wire
    protocol change.

    - N=1: both slots echo the single view's visibility
    - N=2: unchanged — first slot is cam1, second is cam2
    - N>=3: first slot = min of cam[0..N/2), second slot = min of cam[N/2..N)
    """
    n = len(per_view_vis)
    if n == 0:
        return 0.0, 0.0
    if n == 1:
        return per_view_vis[0], per_view_vis[0]
    half = n // 2
    first_half = per_view_vis[:max(half, 1)]
    second_half = per_view_vis[max(half, 1):] or first_half
    return min(first_half), min(second_half)


def _process_landmarks(buf, landmark_sets, mv_calib, resolution, now, refine=False):
    """Extract 2D landmarks from each camera, triangulate, write to SHM.

    ``landmark_sets`` is a list of ``pose_landmarks[0]`` per camera (or
    ``None`` if that camera's detector didn't find a pose this frame).
    ``mv_calib`` is a :class:`MultiViewCalibration` (possibly promoted
    from legacy stereo) or ``None`` for monocular fallback. ``refine``
    triggers non-linear BA on top of DLT.
    """
    from .complementary_filter import JOINT_NAMES
    from .stereo_calibration import triangulate_multiview

    w, h = resolution
    n_views = len(landmark_sets)

    # If calibration and config disagree on camera count, use the overlap.
    usable_views = (
        min(n_views, mv_calib.camera_count) if mv_calib is not None else n_views
    )

    for i, joint_name in enumerate(JOINT_NAMES):
        if i >= len(buf):
            break

        indices = _MP_INDICES.get(joint_name)
        if indices is None:
            _zero_joint(buf, i, now)
            continue

        idx_a, idx_b = indices

        per_view_px: list[np.ndarray] = []
        per_view_vis: list[float] = []
        for view_idx in range(n_views):
            px, vis = _landmark_pixel_and_vis(
                landmark_sets[view_idx], idx_a, idx_b, w, h
            )
            per_view_px.append(px)
            per_view_vis.append(vis)

        confidence = float(np.mean(per_view_vis)) if per_view_vis else 0.0
        cam1_slot, cam2_slot = _summarize_visibility_halves(per_view_vis)

        if mv_calib is not None and usable_views >= 2:
            try:
                points_per_view = [
                    per_view_px[v].reshape(1, 2) for v in range(usable_views)
                ]
                confidences_per_view = [
                    np.array([per_view_vis[v]]) for v in range(usable_views)
                ]
                pts_3d = triangulate_multiview(
                    mv_calib, points_per_view, confidences_per_view,
                    refine=refine,
                )
                pos = pts_3d[0] / 1000.0  # mm → meters
                if not np.all(np.isfinite(pos)):
                    _zero_joint(buf, i, now)
                    continue
                buf[i] = [pos[0], pos[1], pos[2], cam1_slot, cam2_slot, confidence, now]
            except Exception:
                _zero_joint(buf, i, now)
        else:
            # Monocular fallback (single camera or missing calibration):
            # use MediaPipe's relative z from the first available view.
            first_lm = next(
                (lms for lms in landmark_sets if lms is not None), None
            )
            if first_lm is None:
                _zero_joint(buf, i, now)
                continue
            lm_a = first_lm[idx_a]
            z_est = lm_a.z * w
            pos_x = (lm_a.x - 0.5) * 2.0
            pos_y = -(lm_a.y - 0.5) * 2.0
            pos_z = -z_est / w
            buf[i] = [pos_x, pos_y, pos_z, cam1_slot, cam2_slot, confidence * 0.5, now]

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

import logging
import multiprocessing as mp
import time
from dataclasses import dataclass
from multiprocessing import shared_memory
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# 9 joints x (3 position + 1 confidence + 1 timestamp) = 45 floats
JOINT_COUNT = 9
FLOATS_PER_JOINT = 5  # x, y, z, confidence, timestamp
SHM_SIZE = JOINT_COUNT * FLOATS_PER_JOINT * 8  # float64 = 8 bytes
SHM_NAME = "osc_tracking_camera"

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


@dataclass
class CameraConfig:
    """Configuration for the dual camera setup."""
    cam1_index: int = 0
    cam2_index: int = 1
    resolution: tuple[int, int] = (640, 480)
    target_fps: int = 30
    calibration_file: str = "calibration_data/stereo_calib.npz"
    model_path: str = MODEL_PATH_DEFAULT
    model_path_lite: str = MODEL_PATH_LITE


class CameraTracker:
    """Manages camera subprocess and reads triangulated results via shared memory."""

    def __init__(self, config: CameraConfig | None = None):
        self.config = config or CameraConfig()
        self._process: mp.Process | None = None
        self._shm: shared_memory.SharedMemory | None = None
        self._running = mp.Event()

    def start(self) -> None:
        """Start the camera subprocess."""
        if self._process and self._process.is_alive():
            return

        try:
            self._shm = shared_memory.SharedMemory(
                name=SHM_NAME, create=True, size=SHM_SIZE
            )
        except FileExistsError:
            self._shm = shared_memory.SharedMemory(name=SHM_NAME, create=False)

        self._running.set()
        self._process = mp.Process(
            target=_camera_worker,
            args=(self.config, SHM_NAME, self._running),
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

    def read_joints(self) -> dict[str, tuple[np.ndarray, float]] | None:
        """Read latest joint data from shared memory.

        Returns:
            Dict mapping joint name to (position_xyz, confidence),
            or None if shared memory is unavailable.
        """
        if self._shm is None:
            return None

        try:
            buf = np.ndarray(
                (JOINT_COUNT, FLOATS_PER_JOINT),
                dtype=np.float64,
                buffer=self._shm.buf,
            )
        except (ValueError, BufferError):
            logger.warning("Shared memory read failed")
            return None

        from .complementary_filter import JOINT_NAMES

        results = {}
        now = time.monotonic()
        for i, name in enumerate(JOINT_NAMES):
            if i >= JOINT_COUNT:
                break
            x, y, z, conf, ts = buf[i]
            if not np.isfinite(x) or (now - ts) > 0.5:
                continue
            results[name] = (np.array([x, y, z]), float(conf))

        return results

    @property
    def is_alive(self) -> bool:
        return self._process is not None and self._process.is_alive()


def _camera_worker(
    config: CameraConfig,
    shm_name: str,
    running: "mp.synchronize.Event",  # type: ignore[name-defined]
) -> None:
    """Camera subprocess entry point.

    Captures frames from both cameras, runs MediaPipe Pose Landmarker,
    performs stereo triangulation, and writes results to shared memory.
    """
    import cv2

    try:
        shm = shared_memory.SharedMemory(name=shm_name, create=False)
    except FileNotFoundError:
        return

    buf = np.ndarray(
        (JOINT_COUNT, FLOATS_PER_JOINT),
        dtype=np.float64,
        buffer=shm.buf,
    )

    # Initialize cameras
    cap1 = cv2.VideoCapture(config.cam1_index)
    cap2 = cv2.VideoCapture(config.cam2_index)
    for cap in (cap1, cap2):
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.resolution[0])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.resolution[1])

    frame_delay = 1.0 / config.target_fps

    # Load stereo calibration
    from .stereo_calibration import load_calibration
    calib = load_calibration(config.calibration_file)
    if calib is None:
        logging.warning(
            "No stereo calibration found at %s. "
            "Run 'python -m osc_tracking.tools.calibrate' first. "
            "Falling back to monocular depth estimation.",
            config.calibration_file,
        )

    # Initialize MediaPipe Pose Landmarker
    pose1, pose2 = None, None
    try:
        import mediapipe as mp_lib
        from mediapipe.tasks.python import BaseOptions, vision

        model_path = config.model_path
        if not Path(model_path).exists():
            model_path = config.model_path_lite
        if not Path(model_path).exists():
            logging.error(
                "MediaPipe model not found. Download from: "
                "https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker#models "
                "and place at %s",
                config.model_path,
            )
        else:
            options = vision.PoseLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=model_path),
                running_mode=vision.RunningMode.VIDEO,
                num_poses=1,
                min_pose_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            pose1 = vision.PoseLandmarker.create_from_options(options)
            # Need separate instance for camera 2 (stateful)
            pose2 = vision.PoseLandmarker.create_from_options(options)
            logging.info("MediaPipe Pose Landmarker loaded: %s", model_path)
    except Exception as e:
        logging.error("MediaPipe init failed: %s", e)

    consecutive_failures = 0
    frame_ts_ms = 0  # MediaPipe VIDEO mode needs monotonic timestamp in ms

    while running.is_set():
        loop_start = time.monotonic()

        ret1, frame1 = cap1.read()
        ret2, frame2 = cap2.read()

        if not ret1 or not ret2:
            consecutive_failures += 1
            if consecutive_failures >= 3:
                logging.error("Camera capture failed 3x — restarting")
                cap1.release()
                cap2.release()
                time.sleep(1.0)
                cap1 = cv2.VideoCapture(config.cam1_index)
                cap2 = cv2.VideoCapture(config.cam2_index)
                consecutive_failures = 0
            continue

        consecutive_failures = 0
        now = time.monotonic()
        frame_ts_ms += int(1000 / config.target_fps)

        if pose1 is not None and pose2 is not None:
            try:
                import mediapipe as mp_lib

                # Convert BGR → RGB for MediaPipe
                rgb1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2RGB)
                rgb2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2RGB)

                mp_image1 = mp_lib.Image(
                    image_format=mp_lib.ImageFormat.SRGB, data=rgb1
                )
                mp_image2 = mp_lib.Image(
                    image_format=mp_lib.ImageFormat.SRGB, data=rgb2
                )

                result1 = pose1.detect_for_video(mp_image1, frame_ts_ms)
                result2 = pose2.detect_for_video(mp_image2, frame_ts_ms)

                if result1.pose_landmarks and result2.pose_landmarks:
                    lm1 = result1.pose_landmarks[0]
                    lm2 = result2.pose_landmarks[0]

                    _process_landmarks(
                        buf, lm1, lm2, calib, config.resolution, now
                    )
                else:
                    # No pose detected — write zero confidence
                    for i in range(JOINT_COUNT):
                        buf[i] = [0.0, 0.0, 0.0, 0.0, now]

            except Exception as e:
                logging.warning("MediaPipe inference failed: %s", e)
                for i in range(JOINT_COUNT):
                    buf[i] = [0.0, 0.0, 0.0, 0.0, now]
        else:
            # No MediaPipe — write zeros
            for i in range(JOINT_COUNT):
                buf[i] = [0.0, 0.0, 0.0, 0.0, now]

        # Frame rate control
        elapsed = time.monotonic() - loop_start
        sleep_time = frame_delay - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    cap1.release()
    cap2.release()
    if pose1:
        pose1.close()
    if pose2:
        pose2.close()
    shm.close()


def _process_landmarks(buf, lm1, lm2, calib, resolution, now):
    """Extract 2D landmarks, triangulate to 3D, and write to shared memory."""
    from .complementary_filter import JOINT_NAMES
    from .stereo_calibration import triangulate_points

    w, h = resolution

    # MediaPipe landmark index → our joint index mapping
    # Order must match JOINT_NAMES
    mp_indices = {
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

    for i, joint_name in enumerate(JOINT_NAMES):
        if i >= len(buf):
            break

        indices = mp_indices.get(joint_name)
        if indices is None:
            buf[i] = [0.0, 0.0, 0.0, 0.0, now]
            continue

        idx_a, idx_b = indices

        # Get 2D pixel coordinates + visibility from camera 1
        lm1_a = lm1[idx_a]
        px1 = np.array([lm1_a.x * w, lm1_a.y * h])
        vis1 = lm1_a.visibility if hasattr(lm1_a, 'visibility') else 0.5

        # Get 2D pixel coordinates from camera 2
        lm2_a = lm2[idx_a]
        px2 = np.array([lm2_a.x * w, lm2_a.y * h])
        vis2 = lm2_a.visibility if hasattr(lm2_a, 'visibility') else 0.5

        # Average if dual-landmark joint (hips, chest)
        if idx_b is not None:
            lm1_b = lm1[idx_b]
            lm2_b = lm2[idx_b]
            px1 = (px1 + np.array([lm1_b.x * w, lm1_b.y * h])) / 2
            px2 = (px2 + np.array([lm2_b.x * w, lm2_b.y * h])) / 2
            vis1 = (vis1 + (lm1_b.visibility if hasattr(lm1_b, 'visibility') else 0.5)) / 2
            vis2 = (vis2 + (lm2_b.visibility if hasattr(lm2_b, 'visibility') else 0.5)) / 2

        confidence = (vis1 + vis2) / 2.0

        # Triangulate if calibration available
        if calib is not None:
            try:
                pts_3d = triangulate_points(
                    calib,
                    px1.reshape(1, 2),
                    px2.reshape(1, 2),
                )
                pos = pts_3d[0] / 1000.0  # mm → meters
                buf[i] = [pos[0], pos[1], pos[2], confidence, now]
            except Exception:
                buf[i] = [0.0, 0.0, 0.0, 0.0, now]
        else:
            # Fallback: use MediaPipe's estimated z-depth (less accurate)
            z_est = lm1_a.z * w  # MediaPipe z is relative to hip depth
            pos_x = (lm1_a.x - 0.5) * 2.0  # Normalize to roughly -1..1
            pos_y = -(lm1_a.y - 0.5) * 2.0
            pos_z = -z_est / w
            buf[i] = [pos_x, pos_y, pos_z, confidence * 0.5, now]

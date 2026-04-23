"""Stereo camera calibration and triangulation.

Calibrates two webcams using a checkerboard pattern, then provides
stereo triangulation to compute 3D joint positions from 2D landmarks.

Calibration Pipeline:
    1. Capture checkerboard images from both cameras simultaneously
    2. Detect corners in each image pair
    3. Compute per-camera intrinsics (K, distortion)
    4. Compute stereo extrinsics (R, T between cameras)
    5. Save calibration to .npz file

Triangulation Pipeline:
    2D landmarks (cam1) + 2D landmarks (cam2) + calibration
    → cv2.triangulatePoints → 3D world coordinates
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class StereoCalibration:
    """Stereo calibration parameters."""
    K1: np.ndarray        # Camera 1 intrinsic matrix (3x3)
    D1: np.ndarray        # Camera 1 distortion coefficients
    K2: np.ndarray        # Camera 2 intrinsic matrix (3x3)
    D2: np.ndarray        # Camera 2 distortion coefficients
    R: np.ndarray         # Rotation between cameras (3x3)
    T: np.ndarray         # Translation between cameras (3x1)
    image_size: tuple[int, int]  # (width, height)
    reprojection_error: float

    @property
    def P1(self) -> np.ndarray:
        """Projection matrix for camera 1 (3x4)."""
        result: np.ndarray = self.K1 @ np.hstack([np.eye(3), np.zeros((3, 1))])
        return result

    @property
    def P2(self) -> np.ndarray:
        """Projection matrix for camera 2 (3x4)."""
        result: np.ndarray = self.K2 @ np.hstack([self.R, self.T])
        return result


def calibrate_stereo(
    image_pairs: list[tuple[np.ndarray, np.ndarray]],
    board_size: tuple[int, int] = (9, 6),
    square_size_mm: float = 25.0,
) -> StereoCalibration | None:
    """Calibrate a stereo camera pair from checkerboard image pairs.

    Args:
        image_pairs: List of (image_cam1, image_cam2) as numpy arrays.
        board_size: Internal corner count (columns, rows) of the checkerboard.
        square_size_mm: Size of each square in millimeters.

    Returns:
        StereoCalibration if successful, None if calibration failed.
    """
    if len(image_pairs) < 5:
        logger.error("Need at least 5 image pairs, got %d", len(image_pairs))
        return None

    # Prepare object points (checkerboard corners in 3D)
    objp = np.zeros((board_size[0] * board_size[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:board_size[0], 0:board_size[1]].T.reshape(-1, 2)
    objp *= square_size_mm

    obj_points = []  # 3D points
    img_points_1 = []  # 2D points in camera 1
    img_points_2 = []  # 2D points in camera 2

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

    last_gray: np.ndarray | None = None
    for i, (img1, img2) in enumerate(image_pairs):
        gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY) if len(img1.shape) == 3 else img1
        gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY) if len(img2.shape) == 3 else img2
        last_gray = gray1

        ret1, corners1 = cv2.findChessboardCorners(gray1, board_size, None)
        ret2, corners2 = cv2.findChessboardCorners(gray2, board_size, None)

        if ret1 and ret2:
            corners1 = cv2.cornerSubPix(gray1, corners1, (11, 11), (-1, -1), criteria)
            corners2 = cv2.cornerSubPix(gray2, corners2, (11, 11), (-1, -1), criteria)

            obj_points.append(objp)
            img_points_1.append(corners1)
            img_points_2.append(corners2)
        else:
            logger.debug("Pair %d: checkerboard not detected in both images", i)

    if len(obj_points) < 5:
        logger.error("Only %d valid pairs found, need at least 5", len(obj_points))
        return None

    # last_gray is guaranteed set here because len(obj_points) >= 5 implies
    # at least 5 iterations of the loop ran — making it explicit keeps
    # mypy happy and removes the hidden dependency between the early
    # return and the loop variable still being in scope.
    assert last_gray is not None
    h, w = last_gray.shape[:2]
    image_size = (w, h)

    # Per-camera calibration
    _, K1, D1, _, _ = cv2.calibrateCamera(  # type: ignore[call-overload]
        obj_points, img_points_1, image_size,
        np.eye(3, dtype=np.float64), np.zeros(5, dtype=np.float64),
    )
    _, K2, D2, _, _ = cv2.calibrateCamera(  # type: ignore[call-overload]
        obj_points, img_points_2, image_size,
        np.eye(3, dtype=np.float64), np.zeros(5, dtype=np.float64),
    )

    # Stereo calibration
    flags = cv2.CALIB_FIX_INTRINSIC
    ret, K1, D1, K2, D2, R, T, E, F = cv2.stereoCalibrate(
        obj_points, img_points_1, img_points_2,
        K1, D1, K2, D2,
        image_size,
        criteria=criteria,
        flags=flags,
    )

    logger.info("Stereo calibration RMS error: %.4f", ret)

    return StereoCalibration(
        K1=K1, D1=D1, K2=K2, D2=D2,
        R=R, T=T,
        image_size=image_size,
        reprojection_error=ret,
    )


def save_calibration(calib: StereoCalibration, path: str | Path) -> None:
    """Save calibration to .npz file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        path,
        K1=calib.K1, D1=calib.D1,
        K2=calib.K2, D2=calib.D2,
        R=calib.R, T=calib.T,
        image_size=np.array(calib.image_size),
        reprojection_error=np.array(calib.reprojection_error),
    )
    logger.info("Calibration saved to %s", path)


def load_calibration(path: str | Path) -> StereoCalibration | None:
    """Load calibration from .npz file.

    ``allow_pickle=False`` is explicit here (the NumPy default since
    1.16.3) so a future regression to a ``.npy`` object-array cannot
    silently enable pickle deserialisation from a config-supplied path.
    """
    path = Path(path)
    if not path.exists():
        return None
    try:
        data = np.load(path, allow_pickle=False)
        return StereoCalibration(
            K1=data["K1"], D1=data["D1"],
            K2=data["K2"], D2=data["D2"],
            R=data["R"], T=data["T"],
            image_size=tuple(data["image_size"]),
            reprojection_error=float(data["reprojection_error"]),
        )
    except (OSError, KeyError, ValueError):
        # OSError → file corrupt / unreadable; KeyError → missing array;
        # ValueError → bad shape or float conversion. exc_info=True so the
        # traceback survives to a debug log instead of being swallowed.
        logger.warning("Failed to load calibration from %s", path, exc_info=True)
        return None


def triangulate_points(
    calib: StereoCalibration,
    points_cam1: np.ndarray,
    points_cam2: np.ndarray,
) -> np.ndarray:
    """Triangulate 3D points from 2D correspondences.

    Args:
        calib: Stereo calibration parameters.
        points_cam1: Nx2 array of 2D points in camera 1.
        points_cam2: Nx2 array of 2D points in camera 2.

    Returns:
        Nx3 array of 3D points in camera 1's coordinate frame.
    """
    pts1 = points_cam1.T.astype(np.float64)  # 2xN
    pts2 = points_cam2.T.astype(np.float64)  # 2xN

    # Undistort points
    pts1_undist = cv2.undistortPoints(pts1.T.reshape(-1, 1, 2), calib.K1, calib.D1, P=calib.K1)
    pts2_undist = cv2.undistortPoints(pts2.T.reshape(-1, 1, 2), calib.K2, calib.D2, P=calib.K2)

    pts1_undist = pts1_undist.reshape(-1, 2).T  # 2xN
    pts2_undist = pts2_undist.reshape(-1, 2).T  # 2xN

    # Triangulate
    points_4d = cv2.triangulatePoints(calib.P1, calib.P2, pts1_undist, pts2_undist)

    # Convert from homogeneous to 3D. Guard w ~ 0 (points at infinity,
    # parallel-ray degeneracies) — replace with NaN so downstream
    # sanity checks reject the point instead of propagating inf.
    w = points_4d[3:4]
    degenerate = np.abs(w) < 1e-9
    safe_w = np.where(degenerate, 1.0, w)
    points_3d = np.asarray(points_4d[:3] / safe_w)
    if np.any(degenerate):
        points_3d[:, degenerate[0]] = np.nan
    result: np.ndarray = points_3d.T  # Nx3
    return result


def compute_reprojection_error(
    calib: StereoCalibration,
    points_3d: np.ndarray,
    points_cam1: np.ndarray,
    points_cam2: np.ndarray,
) -> float:
    """Compute mean reprojection error for runtime calibration monitoring.

    Args:
        calib: Stereo calibration.
        points_3d: Nx3 triangulated 3D points.
        points_cam1: Nx2 original 2D points from camera 1.
        points_cam2: Nx2 original 2D points from camera 2.

    Returns:
        Mean reprojection error in pixels.
    """
    # Project 3D points back to camera 1
    rvec1 = np.zeros(3)
    tvec1 = np.zeros(3)
    proj1, _ = cv2.projectPoints(points_3d, rvec1, tvec1, calib.K1, calib.D1)
    proj1 = proj1.reshape(-1, 2)

    # Project 3D points to camera 2
    rvec2, _ = cv2.Rodrigues(calib.R)
    proj2, _ = cv2.projectPoints(points_3d, rvec2, calib.T, calib.K2, calib.D2)
    proj2 = proj2.reshape(-1, 2)

    err1 = float(np.mean(np.linalg.norm(proj1 - points_cam1, axis=1)))
    err2 = float(np.mean(np.linalg.norm(proj2 - points_cam2, axis=1)))

    return (err1 + err2) / 2.0


# ---------------------------------------------------------------------------
# Multi-view (3+ cameras) triangulation
# ---------------------------------------------------------------------------


@dataclass
class CameraView:
    """One camera's contribution to a multi-view rig.

    ``R_world`` and ``T_world`` place the camera in the shared world frame
    — the world frame is defined as camera 0's frame (``R = I``, ``T = 0``)
    in :func:`multiview_from_stereo`, matching how stereo triangulation
    already returns points in camera 1's frame.
    """

    K: np.ndarray              # intrinsic (3x3)
    D: np.ndarray              # distortion coefficients
    R_world: np.ndarray        # world → camera rotation (3x3)
    T_world: np.ndarray        # world → camera translation (3x1)

    @property
    def P(self) -> np.ndarray:
        """Projection matrix K [R | T] (3x4)."""
        Rt = np.hstack([self.R_world, self.T_world.reshape(3, 1)])
        return np.asarray(self.K @ Rt)


@dataclass
class MultiViewCalibration:
    """Calibration for N ≥ 2 cameras observing a shared scene.

    All camera poses are expressed relative to ``views[0]`` — that camera
    has ``R = I`` and ``T = 0``, and triangulated points come back in its
    coordinate frame. The 2-camera case is equivalent to the existing
    :class:`StereoCalibration`; see :func:`multiview_from_stereo`.
    """

    views: list[CameraView]
    image_size: tuple[int, int]
    reprojection_error: float = 0.0

    @property
    def camera_count(self) -> int:
        return len(self.views)


def multiview_from_stereo(calib: StereoCalibration) -> MultiViewCalibration:
    """Promote a StereoCalibration to a 2-camera MultiViewCalibration.

    Camera 0 sits at the world origin; camera 1 picks up ``(R, T)`` from
    the stereo rig. This keeps the 2-camera code path identical in
    behavior while letting the same triangulator handle any N.
    """
    view0 = CameraView(
        K=calib.K1,
        D=calib.D1,
        R_world=np.eye(3),
        T_world=np.zeros(3),
    )
    view1 = CameraView(
        K=calib.K2,
        D=calib.D2,
        R_world=calib.R,
        T_world=calib.T.reshape(3),
    )
    return MultiViewCalibration(
        views=[view0, view1],
        image_size=calib.image_size,
        reprojection_error=calib.reprojection_error,
    )


def _refine_single_point(
    initial_xyz: np.ndarray,
    projection_matrices: list[np.ndarray],
    pixels: list[np.ndarray],
    confidences: list[float],
    max_nfev: int = 20,
) -> np.ndarray:
    """Non-linearly refine one 3D point by minimising weighted reprojection.

    Residual is ``sqrt(conf_i) * (observed_ij - projected_ij)`` over every
    view with positive confidence and finite pixel. LM is the standard
    choice for this shape of problem and converges in a handful of
    iterations when the DLT seed is already close.

    Views with a point behind the camera (``Z <= 0``) contribute a large
    fixed penalty so the optimiser is pushed back toward a physically
    reasonable depth. This matters more than it sounds: a half-pixel
    mirror can otherwise drag the estimate through the camera plane.
    """
    try:
        from scipy.optimize import least_squares
    except ImportError:  # pragma: no cover - scipy is a hard dep
        return initial_xyz

    def residuals(xyz: np.ndarray) -> np.ndarray:
        X = np.array([xyz[0], xyz[1], xyz[2], 1.0])
        res: list[float] = []
        for P, uv, conf in zip(projection_matrices, pixels, confidences):
            if conf <= 0.0:
                continue
            if not np.all(np.isfinite(uv)):
                continue
            projected = P @ X
            z = projected[2]
            if z <= 1e-9:
                # Point is on or behind the camera plane — penalise hard.
                res.extend([1e6, 1e6])
                continue
            u_hat = projected[0] / z
            v_hat = projected[1] / z
            sqrt_w = float(np.sqrt(conf))
            res.append(sqrt_w * (float(uv[0]) - u_hat))
            res.append(sqrt_w * (float(uv[1]) - v_hat))
        return np.asarray(res, dtype=np.float64)

    if not np.all(np.isfinite(initial_xyz)):
        return initial_xyz

    try:
        # LM needs m residuals >= n parameters (3). Fall back if too few.
        r0 = residuals(initial_xyz)
        if r0.size < 3:
            return initial_xyz
        result = least_squares(
            residuals,
            initial_xyz.astype(np.float64),
            method="lm",
            max_nfev=max_nfev,
        )
    except (ValueError, np.linalg.LinAlgError):
        return initial_xyz

    refined = np.asarray(result.x, dtype=np.float64)
    if not np.all(np.isfinite(refined)):
        return initial_xyz
    return refined


def refine_multiview(
    calib: MultiViewCalibration,
    initial_points: np.ndarray,
    points_per_view: list[np.ndarray],
    confidences_per_view: list[np.ndarray] | None = None,
    max_nfev: int = 20,
) -> np.ndarray:
    """Non-linear refinement on top of :func:`triangulate_multiview`.

    The DLT solver is fast and unbiased under zero-noise ideal geometry
    but algebraic — its residual doesn't equal pixel reprojection error,
    so under real-world noise the DLT estimate is merely close, not
    optimal. Bundle adjustment (here: point-only BA with fixed camera
    poses) minimises the actual weighted reprojection residual from the
    DLT starting point.

    Points that came back NaN from DLT (under-constrained) are passed
    through unchanged. The un-distorted pixel observations are computed
    once per view and reused, matching the DLT path.
    """
    n_points = initial_points.shape[0]
    if confidences_per_view is None:
        confidences_per_view = [
            np.ones(n_points, dtype=np.float64) for _ in calib.views
        ]

    # Undistort observations once (same as the DLT path).
    undistorted_per_view: list[np.ndarray] = []
    for view, pts in zip(calib.views, points_per_view):
        pts_reshaped = pts.reshape(-1, 1, 2).astype(np.float64)
        undist = cv2.undistortPoints(pts_reshaped, view.K, view.D, P=view.K)
        undistorted_per_view.append(undist.reshape(-1, 2))

    projection_matrices = [view.P for view in calib.views]

    refined = initial_points.copy()
    for pt_idx in range(n_points):
        if not np.all(np.isfinite(initial_points[pt_idx])):
            continue
        pixels_for_pt = [undist[pt_idx] for undist in undistorted_per_view]
        confs_for_pt = [float(c[pt_idx]) for c in confidences_per_view]
        refined[pt_idx] = _refine_single_point(
            initial_points[pt_idx],
            projection_matrices,
            pixels_for_pt,
            confs_for_pt,
            max_nfev=max_nfev,
        )
    return np.asarray(refined)


def triangulate_multiview(
    calib: MultiViewCalibration,
    points_per_view: list[np.ndarray],
    confidences_per_view: list[np.ndarray] | None = None,
    refine: bool = False,
) -> np.ndarray:
    """Triangulate Nx3 world points from N camera views using SVD-based DLT.

    For each 3D point X observed at (u_i, v_i) in camera i with projection
    matrix P_i, two linear constraints apply::

        u_i * P_i[2,:] - P_i[0,:] = 0
        v_i * P_i[2,:] - P_i[1,:] = 0

    Stacking these across all views gives a ``(2K) x 4`` homogeneous system
    whose null-space recovers the 3D point. Points visible in fewer than
    two cameras (or whose system is otherwise degenerate) come back as NaN
    so downstream sanity checks reject them cleanly.

    Args:
        calib: multi-view rig (K camera views in shared world frame).
        points_per_view: length-K list of Nx2 arrays — the same N points
            observed in each camera in the same order. Entries may be NaN
            (or zero-confidence, see below) for views that did not see a
            given point.
        confidences_per_view: optional length-K list of length-N arrays
            with per-observation confidences in [0, 1]. Views contributing
            <= 0 confidence drop out of the system for that point.
        refine: when True, run a non-linear bundle-adjustment refinement
            over the DLT estimate (see :func:`refine_multiview`). Adds
            a few ms per point — worth it for 3+ camera rigs where the
            redundancy can actually reduce reprojection error.

    Returns:
        Nx3 array of 3D points in the world frame defined by ``calib.views[0]``.
    """
    if len(points_per_view) != calib.camera_count:
        raise ValueError(
            f"Expected {calib.camera_count} point arrays, got {len(points_per_view)}"
        )
    if calib.camera_count < 2:
        raise ValueError("Multi-view triangulation requires at least 2 cameras")

    n_points = points_per_view[0].shape[0]
    for arr in points_per_view:
        if arr.shape[0] != n_points:
            raise ValueError("All views must supply the same number of points")

    if confidences_per_view is None:
        confidences_per_view = [
            np.ones(n_points, dtype=np.float64) for _ in calib.views
        ]

    # Undistort each view's points up-front so each call to cv2 happens
    # once per view per call rather than once per point.
    undistorted_per_view: list[np.ndarray] = []
    for view, pts in zip(calib.views, points_per_view):
        pts_reshaped = pts.reshape(-1, 1, 2).astype(np.float64)
        undist = cv2.undistortPoints(pts_reshaped, view.K, view.D, P=view.K)
        undistorted_per_view.append(undist.reshape(-1, 2))

    projection_matrices = [view.P for view in calib.views]

    out = np.full((n_points, 3), np.nan, dtype=np.float64)
    for pt_idx in range(n_points):
        rows: list[np.ndarray] = []
        for view_idx, (P, undist, conf) in enumerate(
            zip(projection_matrices, undistorted_per_view, confidences_per_view)
        ):
            w = float(conf[pt_idx])
            if not (w > 0.0):
                continue
            uv = undist[pt_idx]
            if not np.all(np.isfinite(uv)):
                continue
            u, v = float(uv[0]), float(uv[1])
            sqrt_w = float(np.sqrt(w))
            rows.append(sqrt_w * (u * P[2, :] - P[0, :]))
            rows.append(sqrt_w * (v * P[2, :] - P[1, :]))
        if len(rows) < 4:
            # Need at least 2 views (4 rows) for a well-posed system.
            continue
        A = np.stack(rows, axis=0)
        try:
            _, _, vt = np.linalg.svd(A)
        except np.linalg.LinAlgError:
            continue
        X = vt[-1]
        if abs(X[3]) < 1e-9:
            continue
        out[pt_idx] = X[:3] / X[3]

    if refine:
        out = refine_multiview(
            calib, out, points_per_view, confidences_per_view
        )

    return out


def save_multiview_calibration(
    calib: MultiViewCalibration, path: str | Path
) -> None:
    """Save a multi-view calibration to .npz.

    The saved file embeds the camera count in the array names (``K0``,
    ``D0``, ``R0``, ``T0``, ``K1``, …) so the reader can enumerate views
    without needing a separate index.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    arrays: dict[str, np.ndarray] = {
        "camera_count": np.array(calib.camera_count),
        "image_size": np.array(calib.image_size),
        "reprojection_error": np.array(calib.reprojection_error),
    }
    for i, view in enumerate(calib.views):
        arrays[f"K{i}"] = view.K
        arrays[f"D{i}"] = view.D
        arrays[f"R{i}"] = view.R_world
        arrays[f"T{i}"] = view.T_world
    # np.savez expects **arrays as ndarray kwargs; typeshed's stub narrows
    # the final positional slot to bool, so cast through Any for the call.
    _savez: Any = np.savez
    _savez(path, **arrays)
    logger.info("Multi-view calibration saved to %s (%d cameras)", path, calib.camera_count)


def load_multiview_calibration(path: str | Path) -> MultiViewCalibration | None:
    """Load a multi-view calibration written by :func:`save_multiview_calibration`.

    ``allow_pickle=False`` matches :func:`load_calibration` — the loader
    refuses object arrays so a config-supplied path cannot smuggle in a
    pickle payload.
    """
    path = Path(path)
    if not path.exists():
        return None
    try:
        data = np.load(path, allow_pickle=False)
        n = int(data["camera_count"])
        views = [
            CameraView(
                K=data[f"K{i}"],
                D=data[f"D{i}"],
                R_world=data[f"R{i}"],
                T_world=data[f"T{i}"],
            )
            for i in range(n)
        ]
        return MultiViewCalibration(
            views=views,
            image_size=tuple(data["image_size"]),
            reprojection_error=float(data["reprojection_error"]),
        )
    except (OSError, KeyError, ValueError):
        logger.warning(
            "Failed to load multi-view calibration from %s", path, exc_info=True
        )
        return None

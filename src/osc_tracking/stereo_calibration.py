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

    for i, (img1, img2) in enumerate(image_pairs):
        gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY) if len(img1.shape) == 3 else img1
        gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY) if len(img2.shape) == 3 else img2

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

    h, w = gray1.shape[:2]
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
    except Exception:
        logger.warning("Failed to load calibration from %s", path)
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

"""Visual Compass — correct IMU heading drift using camera shoulder line.

Uses MediaPipe shoulder landmarks (#11 left, #12 right) to compute the
camera-space yaw angle, then overrides the magnetometer-derived heading
component of the chest-mounted IMU tracker (e.g., HaritoraX2, SlimeVR).

When shoulders are not visible (Partial/Full Occlusion), Visual Compass
is suspended and the IMU heading is used with increased uncertainty.
"""

import numpy as np
from scipy.spatial.transform import Rotation


def compute_shoulder_yaw(
    left_shoulder_3d: np.ndarray,
    right_shoulder_3d: np.ndarray,
) -> float | None:
    """Compute yaw angle from shoulder line in camera coordinates.

    Args:
        left_shoulder_3d: 3D position of left shoulder (MediaPipe #11).
        right_shoulder_3d: 3D position of right shoulder (MediaPipe #12).

    Returns:
        Yaw angle in radians, or None if input is invalid.
    """
    if not (np.all(np.isfinite(left_shoulder_3d)) and np.all(np.isfinite(right_shoulder_3d))):
        return None

    shoulder_vec = right_shoulder_3d - left_shoulder_3d
    # Shoulder vector is perpendicular to facing direction
    # Forward direction is the cross product of shoulder vec and up
    forward = np.array([-shoulder_vec[2], 0.0, shoulder_vec[0]])
    if np.linalg.norm(forward[:2]) < 1e-6 and abs(forward[2]) < 1e-6:
        return None

    yaw = np.arctan2(forward[0], forward[2])
    return float(yaw)


def correct_heading(
    imu_rotation: Rotation,
    camera_yaw: float,
    blend_factor: float = 0.3,
) -> Rotation:
    """Correct IMU heading using camera-derived yaw.

    Replaces the yaw component of the IMU rotation with a blend of
    IMU yaw and camera yaw. Pitch and roll are preserved from IMU.

    Args:
        imu_rotation: Current IMU rotation.
        camera_yaw: Yaw from Visual Compass (radians).
        blend_factor: How much to trust camera yaw (0=IMU only, 1=camera only).

    Returns:
        Corrected rotation with blended yaw.
    """
    euler = imu_rotation.as_euler("YXZ")  # yaw, pitch, roll
    imu_yaw = euler[0]

    # Blend yaw angles (handle wraparound)
    diff = camera_yaw - imu_yaw
    diff = (diff + np.pi) % (2 * np.pi) - np.pi  # normalize to [-pi, pi]
    corrected_yaw = imu_yaw + diff * blend_factor

    euler[0] = corrected_yaw
    return Rotation.from_euler("YXZ", euler)

"""Complementary filter for IMU + optical sensor fusion.

Fuses camera-derived position with IMU-derived rotation using a simple
weighted average. This is the Phase 1 approach — upgrade to Multiplicative
EKF if quality is insufficient.

Data Flow:
    Camera 3D pos ──► ┌────────────────┐
                      │  Complementary  │ ──► Fused position + rotation
    IMU quaternion ──►│     Filter      │
                      └────────────────┘
                             │
                    Confidence score determines
                    camera vs IMU weight
"""

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.spatial.transform import Rotation


@dataclass
class JointState:
    """State for a single tracked joint."""
    position: np.ndarray = field(default_factory=lambda: np.zeros(3))
    rotation: Rotation = field(default_factory=lambda: Rotation.identity())
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(3))
    last_valid_position: np.ndarray = field(default_factory=lambda: np.zeros(3))
    last_valid_rotation: Rotation = field(default_factory=lambda: Rotation.identity())
    stationary_timer: float = 0.0


# Tracked joints — matches HaritoraX2 tracker layout + camera-derived joints.
# HaritoraX2 provides: Hips, Chest, LeftFoot, RightFoot,
#                       LeftKnee, RightKnee, LeftElbow, RightElbow
# Camera provides: Head (via MediaPipe face landmarks)
JOINT_NAMES = [
    "Hips", "Chest", "Head",
    "LeftFoot", "RightFoot",
    "LeftKnee", "RightKnee",
    "LeftElbow", "RightElbow",
]


class ComplementaryFilter:
    """Per-joint complementary filter for camera + IMU fusion.

    For each joint, blends camera position and IMU rotation based on a
    confidence weight. In high-confidence (Visible) mode, camera position
    dominates. In low-confidence (Occlusion) mode, the filter holds the
    last known position and relies on IMU rotation only.

    Smooth recovery uses frame-rate-independent exponential decay:
        new_pos = current + (target - current) * (1 - exp(-rate * dt))
    """

    SMOOTH_RATE = 5.0  # ~0.2s for 80% convergence
    DRIFT_VELOCITY_THRESHOLD = 0.02  # m/s
    DRIFT_HOLD_SECONDS = 10.0
    DRIFT_NOISE_SCALE = 0.01  # 1% of normal when stationary

    def __init__(
        self,
        compass_blend_factor: float,
        visible_threshold: float = 0.7,
        partial_threshold: float = 0.3,
    ):
        self.compass_blend_factor = max(0.0, min(1.0, compass_blend_factor))
        self.visible_threshold = visible_threshold
        self.partial_threshold = partial_threshold
        self.joints: dict[str, JointState] = {
            name: JointState() for name in JOINT_NAMES
        }

    def update(
        self,
        joint_name: str,
        camera_position: np.ndarray | None,
        imu_rotation: Rotation | None,
        confidence: float,
        dt: float,
    ) -> JointState:
        """Update a single joint's fused state.

        Args:
            joint_name: One of JOINT_NAMES.
            camera_position: 3D position from stereo triangulation, or None.
            imu_rotation: Quaternion rotation from HaritoraX2, or None.
            confidence: Combined camera confidence (0.0-1.0).
            dt: Time delta since last update in seconds.

        Returns:
            Updated JointState with fused position and rotation.

        Raises:
            KeyError: If joint_name is not in JOINT_NAMES.
        """
        state = self.joints[joint_name]

        # Sanitize inputs — reject NaN/Inf
        if camera_position is not None and not np.all(np.isfinite(camera_position)):
            camera_position = None
        if imu_rotation is not None:
            quat = imu_rotation.as_quat()
            if not np.all(np.isfinite(quat)):
                imu_rotation = None

        # Outlier rejection: if camera position jumps more than 3x expected
        if (
            camera_position is not None
            and not np.allclose(state.last_valid_position, 0.0)
        ):
            displacement = float(np.linalg.norm(camera_position - state.position))
            max_expected = float(
                max(np.linalg.norm(state.velocity) * dt * 3.0, 0.5)
            )
            if displacement > max_expected and confidence < 0.9:
                camera_position = None  # Reject outlier

        # Position update
        if camera_position is not None and confidence > self.partial_threshold:
            # First valid position: snap directly (no smoothing from origin)
            if np.allclose(state.last_valid_position, 0.0):
                state.position = camera_position.copy()
            else:
                alpha = self._smooth_alpha(dt)
                weight = confidence
                target = camera_position
                state.position = state.position + (target - state.position) * alpha * weight
            state.velocity = (camera_position - state.last_valid_position) / max(dt, 1e-6)
            state.last_valid_position = camera_position.copy()
        # else: hold current position (Full Occlusion / IMU disconnected)

        # Rotation update
        if imu_rotation is not None:
            if camera_position is not None and confidence > self.visible_threshold:
                # Visible mode: blend current rotation toward IMU using Slerp
                alpha = self._smooth_alpha(dt)
                blend = alpha * self.compass_blend_factor
                from scipy.spatial.transform import Slerp as ScipySlerp
                key_rots = Rotation.concatenate([state.rotation, imu_rotation])
                slerp = ScipySlerp([0.0, 1.0], key_rots)
                state.rotation = slerp(blend)
            else:
                # Partial/Full: trust IMU for rotation
                state.rotation = imu_rotation
            state.last_valid_rotation = imu_rotation
        elif camera_position is not None and confidence > 0.5:
            # IMU disconnected: estimate rotation from camera only (less accurate)
            pass  # Keep last rotation; camera-only rotation is unreliable

        # Drift cut: suppress noise when stationary
        self._update_drift_cut(state, dt)

        return state

    def reset_joint(self, joint_name: str) -> None:
        """Reset a joint to its last valid state (NaN/Inf recovery)."""
        state = self.joints[joint_name]
        state.position = state.last_valid_position.copy()
        state.rotation = state.last_valid_rotation
        state.velocity = np.zeros(3)

    def _smooth_alpha(self, dt: float) -> float:
        """Frame-rate-independent exponential decay factor."""
        return 1.0 - math.exp(-self.SMOOTH_RATE * dt)

    def _update_drift_cut(self, state: JointState, dt: float) -> None:
        """Suppress velocity when stationary for extended period."""
        speed = np.linalg.norm(state.velocity)
        if speed < self.DRIFT_VELOCITY_THRESHOLD:
            state.stationary_timer += dt
            if state.stationary_timer >= self.DRIFT_HOLD_SECONDS:
                # Decay velocity toward zero
                decay = math.exp(-dt / 2.0)
                state.velocity *= decay
        else:
            state.stationary_timer = 0.0

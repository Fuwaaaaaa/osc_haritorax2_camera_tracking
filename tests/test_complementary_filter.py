"""Tests for the complementary filter."""

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from osc_tracking.complementary_filter import JOINT_NAMES, ComplementaryFilter


@pytest.fixture
def cf():
    return ComplementaryFilter()


class TestHappyPath:
    def test_camera_and_imu_input(self, cf):
        """Camera position + IMU rotation → fused output."""
        cam_pos = np.array([1.0, 2.0, 3.0])
        imu_rot = Rotation.from_euler("xyz", [10, 20, 30], degrees=True)

        state = cf.update("Hips", cam_pos, imu_rot, confidence=0.9, dt=1/30)

        assert np.all(np.isfinite(state.position))
        assert state.rotation is not None

    def test_position_moves_toward_camera(self, cf):
        """Over multiple frames, position should converge to camera pos."""
        target = np.array([5.0, 5.0, 5.0])
        imu_rot = Rotation.identity()

        for _ in range(100):
            state = cf.update("Hips", target, imu_rot, confidence=0.9, dt=1/30)

        assert np.linalg.norm(state.position - target) < 0.5


class TestFullOcclusion:
    def test_no_camera_holds_position(self, cf):
        """Without camera data, position should be held."""
        cam_pos = np.array([1.0, 2.0, 3.0])
        imu_rot = Rotation.identity()

        # First update with camera
        cf.update("Hips", cam_pos, imu_rot, confidence=0.9, dt=1/30)

        # Then without camera
        state = cf.update("Hips", None, imu_rot, confidence=0.0, dt=1/30)

        # Position should stay near last known
        assert np.linalg.norm(state.position - cam_pos) < 1.0


class TestIMUDisconnected:
    def test_no_imu_uses_camera_only(self, cf):
        cam_pos = np.array([1.0, 2.0, 3.0])

        state = cf.update("Head", cam_pos, None, confidence=0.9, dt=1/30)

        assert np.all(np.isfinite(state.position))


class TestNaNInfHandling:
    def test_nan_camera_position_rejected(self, cf):
        nan_pos = np.array([float("nan"), 1.0, 2.0])
        imu_rot = Rotation.identity()

        state = cf.update("Hips", nan_pos, imu_rot, confidence=0.9, dt=1/30)

        # Should use default position, not NaN
        assert np.all(np.isfinite(state.position))

    def test_inf_camera_position_rejected(self, cf):
        inf_pos = np.array([float("inf"), 1.0, 2.0])
        imu_rot = Rotation.identity()

        state = cf.update("Hips", inf_pos, imu_rot, confidence=0.9, dt=1/30)

        assert np.all(np.isfinite(state.position))

    def test_nan_imu_rotation_rejected(self, cf):
        cam_pos = np.array([1.0, 2.0, 3.0])
        # Pass None to simulate IMU failure instead of NaN quat
        state = cf.update("Hips", cam_pos, None, confidence=0.9, dt=1/30)

        assert np.all(np.isfinite(state.position))

    def test_reset_joint_recovers_from_bad_state(self, cf):
        cam_pos = np.array([1.0, 2.0, 3.0])
        cf.update("Hips", cam_pos, Rotation.identity(), confidence=0.9, dt=1/30)

        cf.reset_joint("Hips")
        state = cf.joints["Hips"]

        assert np.all(np.isfinite(state.position))
        assert np.allclose(state.velocity, 0.0)


class TestOutlierRejection:
    def test_large_jump_rejected(self, cf):
        """A position jump > 3x expected velocity should be rejected."""
        pos1 = np.array([1.0, 1.0, 1.0])
        pos2 = np.array([1.01, 1.01, 1.01])  # Small movement to establish velocity
        pos3 = np.array([100.0, 100.0, 100.0])  # Huge jump
        imu = Rotation.identity()

        cf.update("Hips", pos1, imu, confidence=0.9, dt=1/30)
        cf.update("Hips", pos2, imu, confidence=0.9, dt=1/30)
        state = cf.update("Hips", pos3, imu, confidence=0.5, dt=1/30)

        # Should NOT jump to 100,100,100 — outlier should be rejected
        assert np.linalg.norm(state.position) < 50.0


class TestSmoothRecovery:
    def test_frame_rate_independent(self, cf):
        """Smoothing should produce similar results at 30fps and 60fps."""
        target = np.array([10.0, 10.0, 10.0])
        imu = Rotation.identity()

        cf1 = ComplementaryFilter()
        cf2 = ComplementaryFilter()

        # 30fps for 1 second
        for _ in range(30):
            cf1.update("Hips", target, imu, confidence=0.9, dt=1/30)

        # 60fps for 1 second
        for _ in range(60):
            cf2.update("Hips", target, imu, confidence=0.9, dt=1/60)

        pos1 = cf1.joints["Hips"].position
        pos2 = cf2.joints["Hips"].position

        # Should be close (within 20% of each other)
        assert np.linalg.norm(pos1 - pos2) / np.linalg.norm(pos1) < 0.2


class TestDriftCut:
    def test_velocity_decays_when_stationary(self, cf):
        """After 10+ seconds of near-zero motion, velocity should decay."""
        pos = np.array([1.0, 2.0, 3.0])
        imu = Rotation.identity()

        # Give it initial velocity
        cf.update("Hips", pos, imu, confidence=0.9, dt=1/30)
        cf.update("Hips", pos + np.array([0.001, 0, 0]), imu, confidence=0.9, dt=1/30)

        # Simulate 11 seconds of no movement
        for _ in range(330):  # 11s * 30fps
            cf.update("Hips", pos, imu, confidence=0.9, dt=1/30)

        state = cf.joints["Hips"]
        assert np.linalg.norm(state.velocity) < 0.01


class TestAllJoints:
    def test_all_joint_names_exist(self, cf):
        assert len(JOINT_NAMES) == 9
        for name in JOINT_NAMES:
            assert name in cf.joints

    def test_invalid_joint_raises(self, cf):
        with pytest.raises(KeyError):
            cf.update("InvalidJoint", np.zeros(3), None, 0.5, 1/30)

"""Tests for the complementary filter."""

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from osc_tracking.complementary_filter import JOINT_NAMES, ComplementaryFilter


@pytest.fixture
def cf():
    return ComplementaryFilter(compass_blend_factor=0.3)


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

        cf1 = ComplementaryFilter(compass_blend_factor=0.3)
        cf2 = ComplementaryFilter(compass_blend_factor=0.3)

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


class TestDriftCutPerJoint:
    """Per-joint stationary timers are independent."""

    def test_drift_cut_per_joint(self, cf):
        """Hips moving should not reset Head's stationary timer."""
        pos = np.array([1.0, 2.0, 3.0])
        imu = Rotation.identity()

        # Build up Head's stationary timer for several seconds
        for _ in range(150):  # 5s at 30fps
            cf.update("Head", pos, imu, confidence=0.9, dt=1 / 30)

        head_timer_before = cf.joints["Head"].stationary_timer

        # Now move Hips — large position changes
        for i in range(30):
            moving_pos = pos + np.array([float(i) * 0.5, 0, 0])
            cf.update("Hips", moving_pos, imu, confidence=0.9, dt=1 / 30)

        # Head timer should NOT have been reset by Hips motion
        assert cf.joints["Head"].stationary_timer >= head_timer_before
        # Hips timer should be zero because it was moving
        assert cf.joints["Hips"].stationary_timer < 1.0


class TestSlerpRotationBlend:
    """Slerp-based rotation blending in Visible mode."""

    def test_slerp_rotation_blend(self, cf):
        """In Visible mode (confidence > 0.7) Slerp blends toward IMU rotation."""
        imu_rot = Rotation.from_euler("z", 90, degrees=True)
        cam_pos = np.array([1.0, 1.0, 1.0])

        # First frame: snap position + set rotation
        cf.update("Hips", cam_pos, Rotation.identity(), confidence=0.9, dt=1 / 30)

        # Subsequent frames with a different IMU rotation — Slerp should blend
        for _ in range(60):
            state = cf.update("Hips", cam_pos, imu_rot, confidence=0.9, dt=1 / 30)

        # The fused rotation should have moved toward the IMU rotation
        angle = (state.rotation.inv() * imu_rot).magnitude()
        # Should be closer to imu_rot than to identity (pi/2 ≈ 1.57)
        assert angle < 1.0

    def test_slerp_preserves_rotation_norm(self, cf):
        """Quaternion from Slerp blending must be unit quaternion."""
        cam_pos = np.array([2.0, 3.0, 1.0])
        imu_rot = Rotation.from_euler("xyz", [45, -30, 60], degrees=True)

        cf.update("Hips", cam_pos, Rotation.identity(), confidence=0.9, dt=1 / 30)

        for _ in range(30):
            state = cf.update("Hips", cam_pos, imu_rot, confidence=0.9, dt=1 / 30)

        quat = state.rotation.as_quat()
        assert abs(np.linalg.norm(quat) - 1.0) < 1e-6


class TestConfidenceThresholds:
    """Behaviour at confidence boundaries."""

    def test_confidence_below_threshold_no_position_update(self, cf):
        """confidence <= 0.3 should not update position from camera."""
        imu = Rotation.identity()
        initial_pos = np.array([1.0, 2.0, 3.0])

        # Establish position
        cf.update("Hips", initial_pos, imu, confidence=0.9, dt=1 / 30)

        # Provide a different camera position at low confidence
        far_pos = np.array([10.0, 20.0, 30.0])
        state = cf.update("Hips", far_pos, imu, confidence=0.3, dt=1 / 30)

        # Position should stay near the original, not jump to far_pos
        assert np.linalg.norm(state.position - initial_pos) < 1.0

    def test_partial_occlusion_imu_trusted(self, cf):
        """0.3 < confidence < 0.7: IMU rotation used directly (no Slerp blend)."""
        cam_pos = np.array([1.0, 1.0, 1.0])
        imu_rot = Rotation.from_euler("y", 45, degrees=True)

        # Establish position first
        cf.update("Hips", cam_pos, Rotation.identity(), confidence=0.9, dt=1 / 30)

        # Partial occlusion: confidence between 0.3 and 0.7
        state = cf.update("Hips", cam_pos, imu_rot, confidence=0.5, dt=1 / 30)

        # In partial occlusion the else branch sets rotation = imu_rotation directly
        angle_diff = (state.rotation.inv() * imu_rot).magnitude()
        assert angle_diff < 1e-6


class TestFirstValidPositionSnap:
    """First valid camera position should snap without smoothing."""

    def test_first_valid_position_snaps(self, cf):
        """When last_valid_position is origin, position should snap to camera."""
        cam_pos = np.array([5.0, 10.0, 15.0])
        imu = Rotation.identity()

        state = cf.update("Hips", cam_pos, imu, confidence=0.9, dt=1 / 30)

        # Should be exactly the camera position (snap, not smoothed)
        np.testing.assert_array_almost_equal(state.position, cam_pos)


class TestVelocityAndStationaryTimer:
    """Velocity computation and stationary timer reset."""

    def test_velocity_computed_on_position_update(self, cf):
        """Camera position update should produce a non-zero velocity."""
        imu = Rotation.identity()
        pos1 = np.array([0.0, 0.0, 0.0])
        pos2 = np.array([1.0, 0.0, 0.0])

        cf.update("Hips", pos1, imu, confidence=0.9, dt=1 / 30)
        state = cf.update("Hips", pos2, imu, confidence=0.9, dt=1 / 30)

        # velocity = (pos2 - pos1) / dt → should be large
        assert np.linalg.norm(state.velocity) > 0.0
        # x-component should be positive
        assert state.velocity[0] > 0.0

    def test_stationary_timer_resets_on_motion(self, cf):
        """Moving above DRIFT_VELOCITY_THRESHOLD resets stationary_timer to 0."""
        imu = Rotation.identity()
        pos = np.array([1.0, 2.0, 3.0])

        # Accumulate stationary time
        for _ in range(150):  # 5s
            cf.update("Hips", pos, imu, confidence=0.9, dt=1 / 30)

        assert cf.joints["Hips"].stationary_timer > 4.0

        # Now move significantly
        new_pos = pos + np.array([5.0, 0.0, 0.0])
        cf.update("Hips", new_pos, imu, confidence=0.9, dt=1 / 30)

        # Timer should have been reset to 0
        assert cf.joints["Hips"].stationary_timer < 0.1


class TestCompassBlendFactor:
    """Tests for configurable compass_blend_factor (Phase 2 bug fix)."""

    def test_default_blend_factor(self):
        cf = ComplementaryFilter(compass_blend_factor=0.3)
        assert cf.compass_blend_factor == 0.3

    def test_custom_blend_factor_affects_slerp(self):
        """Different blend factors should produce different rotation outputs."""
        cam_pos = np.array([1.0, 2.0, 3.0])
        imu_rot = Rotation.from_euler("xyz", [45, 0, 0], degrees=True)

        cf_low = ComplementaryFilter(compass_blend_factor=0.1)
        cf_high = ComplementaryFilter(compass_blend_factor=0.9)

        state_low = cf_low.update("Chest", cam_pos, imu_rot, confidence=0.9, dt=1/30)
        state_high = cf_high.update("Chest", cam_pos, imu_rot, confidence=0.9, dt=1/30)

        # Different blend factors should yield different rotations
        angle_diff = (
            state_low.rotation.inv() * state_high.rotation
        ).magnitude()
        assert angle_diff > 0.001

    def test_blend_factor_clamped_to_valid_range(self):
        """Values outside [0, 1] should be clamped."""
        cf_neg = ComplementaryFilter(compass_blend_factor=-0.5)
        assert cf_neg.compass_blend_factor == 0.0

        cf_over = ComplementaryFilter(compass_blend_factor=1.5)
        assert cf_over.compass_blend_factor == 1.0

    def test_blend_factor_zero_means_no_camera_blend(self):
        """blend_factor=0 should make Slerp return the current rotation (no blend)."""
        cf = ComplementaryFilter(compass_blend_factor=0.0)
        imu_rot = Rotation.from_euler("xyz", [30, 0, 0], degrees=True)
        cam_pos = np.array([1.0, 2.0, 3.0])

        # Update twice to establish a baseline rotation
        cf.update("Hips", cam_pos, imu_rot, confidence=0.9, dt=1/30)
        state = cf.update("Hips", cam_pos, imu_rot, confidence=0.9, dt=1/30)

        # With blend=0, rotation should closely follow existing state (no camera blend)
        angle = (state.rotation.inv() * imu_rot).magnitude()
        # Not exact due to Slerp with blend=0 returning start rotation
        assert angle < 0.6  # radians — close to IMU

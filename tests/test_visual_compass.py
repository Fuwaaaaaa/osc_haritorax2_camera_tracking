"""Tests for the Visual Compass."""

import numpy as np
from scipy.spatial.transform import Rotation

from osc_tracking.visual_compass import compute_shoulder_yaw, correct_heading


class TestComputeShoulderYaw:
    def test_shoulders_facing_forward(self):
        left = np.array([-0.2, 1.5, 1.0])
        right = np.array([0.2, 1.5, 1.0])
        yaw = compute_shoulder_yaw(left, right)
        assert yaw is not None
        assert abs(yaw) < 0.5  # Roughly forward

    def test_shoulders_turned_90_degrees(self):
        left = np.array([0.0, 1.5, -0.2])
        right = np.array([0.0, 1.5, 0.2])
        yaw = compute_shoulder_yaw(left, right)
        assert yaw is not None

    def test_nan_input_returns_none(self):
        left = np.array([float("nan"), 1.5, 1.0])
        right = np.array([0.2, 1.5, 1.0])
        assert compute_shoulder_yaw(left, right) is None

    def test_zero_vector_returns_none(self):
        same = np.array([0.0, 1.5, 0.0])
        assert compute_shoulder_yaw(same, same) is None


class TestCorrectHeading:
    def test_correction_blends_yaw(self):
        imu = Rotation.from_euler("YXZ", [0.5, 0.1, 0.0])
        camera_yaw = 0.0

        corrected = correct_heading(imu, camera_yaw, blend_factor=0.5)
        corrected_euler = corrected.as_euler("YXZ")

        # Yaw should move toward camera_yaw (0.0)
        assert abs(corrected_euler[0]) < abs(0.5)

    def test_zero_blend_preserves_imu(self):
        imu = Rotation.from_euler("YXZ", [0.5, 0.1, 0.0])
        corrected = correct_heading(imu, 0.0, blend_factor=0.0)
        corrected_euler = corrected.as_euler("YXZ")

        assert abs(corrected_euler[0] - 0.5) < 0.01

    def test_full_blend_matches_camera(self):
        imu = Rotation.from_euler("YXZ", [0.5, 0.1, 0.0])
        corrected = correct_heading(imu, 0.0, blend_factor=1.0)
        corrected_euler = corrected.as_euler("YXZ")

        assert abs(corrected_euler[0]) < 0.01

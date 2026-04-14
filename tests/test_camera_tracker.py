"""Tests for camera_tracker.py — SharedMemory, per-camera confidence, lifecycle."""

import time
from multiprocessing import shared_memory
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from osc_tracking.camera_tracker import (
    FLOATS_PER_JOINT,
    JOINT_COUNT,
    SHM_SIZE,
    CameraConfig,
    CameraTracker,
)
from osc_tracking.complementary_filter import JOINT_NAMES


class TestConstants:
    """Verify module-level constants are consistent."""

    def test_joint_count(self):
        assert JOINT_COUNT == 9

    def test_floats_per_joint(self):
        # x, y, z, cam1_vis, cam2_vis, combined_conf, timestamp
        assert FLOATS_PER_JOINT == 7

    def test_shm_size(self):
        assert SHM_SIZE == JOINT_COUNT * FLOATS_PER_JOINT * 8

    def test_joint_names_length(self):
        assert len(JOINT_NAMES) == JOINT_COUNT


class TestPerCameraConfidence:
    """Test that read_joints returns per-camera confidence values."""

    @pytest.fixture
    def tracker_with_shm(self):
        tracker = CameraTracker()
        shm_name = f"test_osc_cam_{id(tracker)}"
        shm = shared_memory.SharedMemory(name=shm_name, create=True, size=SHM_SIZE)
        tracker._shm = shm
        tracker._shm_name = shm_name
        yield tracker, shm
        try:
            shm.close()
            shm.unlink()
        except FileNotFoundError:
            pass

    def test_read_returns_per_camera_confidence(self, tracker_with_shm):
        """read_joints should return (position, combined_conf, cam1_conf, cam2_conf)."""
        tracker, shm = tracker_with_shm
        buf = np.ndarray(
            (JOINT_COUNT, FLOATS_PER_JOINT), dtype=np.float64, buffer=shm.buf
        )
        now = time.monotonic()
        for i in range(JOINT_COUNT):
            # x, y, z, cam1_vis, cam2_vis, combined, timestamp
            buf[i] = [1.0, 2.0, 3.0, 0.9, 0.7, 0.8, now]

        result = tracker.read_joints()
        assert result is not None
        assert len(result) > 0
        for name, data in result.items():
            assert len(data) == 4  # (pos, combined, cam1, cam2)
            pos, combined, cam1, cam2 = data
            assert np.all(np.isfinite(pos))
            assert cam1 == pytest.approx(0.9)
            assert cam2 == pytest.approx(0.7)
            assert combined == pytest.approx(0.8)

    def test_asymmetric_camera_confidence(self, tracker_with_shm):
        """Different cam1/cam2 confidence should be preserved."""
        tracker, shm = tracker_with_shm
        buf = np.ndarray(
            (JOINT_COUNT, FLOATS_PER_JOINT), dtype=np.float64, buffer=shm.buf
        )
        now = time.monotonic()
        # Camera 1 sees well, camera 2 is occluded
        buf[0] = [1.0, 2.0, 3.0, 0.95, 0.1, 0.525, now]
        # Rest are zero/stale
        for i in range(1, JOINT_COUNT):
            buf[i] = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

        result = tracker.read_joints()
        assert result is not None
        joint_name = JOINT_NAMES[0]
        assert joint_name in result
        _, _, cam1, cam2 = result[joint_name]
        assert cam1 == pytest.approx(0.95)
        assert cam2 == pytest.approx(0.1)

    def test_stale_data_filtered(self, tracker_with_shm):
        """Data older than 0.5s should be filtered out."""
        tracker, shm = tracker_with_shm
        buf = np.ndarray(
            (JOINT_COUNT, FLOATS_PER_JOINT), dtype=np.float64, buffer=shm.buf
        )
        old_time = time.monotonic() - 1.0
        for i in range(JOINT_COUNT):
            buf[i] = [1.0, 2.0, 3.0, 0.9, 0.9, 0.9, old_time]

        result = tracker.read_joints()
        assert result is not None
        assert len(result) == 0

    def test_nan_data_filtered(self, tracker_with_shm):
        """NaN position values should be filtered out."""
        tracker, shm = tracker_with_shm
        buf = np.ndarray(
            (JOINT_COUNT, FLOATS_PER_JOINT), dtype=np.float64, buffer=shm.buf
        )
        now = time.monotonic()
        for i in range(JOINT_COUNT):
            buf[i] = [float("nan"), 2.0, 3.0, 0.9, 0.9, 0.9, now]

        result = tracker.read_joints()
        assert result is not None
        assert len(result) == 0

    def test_no_shm_returns_none(self):
        tracker = CameraTracker()
        assert tracker.read_joints() is None


class TestCameraConfig:
    def test_defaults(self):
        cfg = CameraConfig()
        assert cfg.cam1_index == 0
        assert cfg.cam2_index == 1
        assert cfg.resolution == (640, 480)
        assert cfg.target_fps == 30


class TestLifecycle:
    @patch("osc_tracking.camera_tracker.mp.Process")
    def test_start_creates_process(self, mock_proc_cls):
        tracker = CameraTracker()
        mock_proc = MagicMock()
        mock_proc.is_alive.return_value = False
        mock_proc_cls.return_value = mock_proc
        tracker.start()
        assert tracker._shm is not None
        mock_proc.start.assert_called_once()
        tracker.stop()

    @patch("osc_tracking.camera_tracker.mp.Process")
    def test_stop_cleans_up(self, mock_proc_cls):
        tracker = CameraTracker()
        mock_proc = MagicMock()
        mock_proc.is_alive.return_value = True
        mock_proc_cls.return_value = mock_proc
        tracker.start()
        tracker.stop()
        mock_proc.join.assert_called_once()
        assert tracker._shm is None
        assert tracker._process is None

    def test_is_alive_without_start(self):
        tracker = CameraTracker()
        assert tracker.is_alive is False

"""Tests for camera_tracker.py — SharedMemory, per-camera confidence, lifecycle."""

import time
from multiprocessing import shared_memory
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from osc_tracking.camera_tracker import (
    FLOATS_PER_JOINT,
    JOINT_COUNT,
    SHM_NAME,
    SHM_SIZE,
    CameraConfig,
    CameraTracker,
    _next_monotonic_ms,
    _unique_shm_name,
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


class TestCameraConfig:
    def test_defaults(self):
        cfg = CameraConfig()
        assert cfg.cam1_index == 0
        assert cfg.cam2_index == 1
        assert cfg.resolution == (640, 480)
        assert cfg.target_fps == 30

    def test_custom_values(self):
        cfg = CameraConfig(cam1_index=2, cam2_index=3, target_fps=60)
        assert cfg.cam1_index == 2
        assert cfg.target_fps == 60


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

    def test_mixed_valid_and_invalid(self, tracker_with_shm):
        """Some valid, some stale, some NaN — only valid returned."""
        tracker, shm = tracker_with_shm
        buf = np.ndarray(
            (JOINT_COUNT, FLOATS_PER_JOINT), dtype=np.float64, buffer=shm.buf
        )
        now = time.monotonic()
        # Joint 0: valid
        buf[0] = [1.0, 2.0, 3.0, 0.9, 0.9, 0.9, now]
        # Joint 1: stale
        buf[1] = [1.0, 2.0, 3.0, 0.9, 0.9, 0.9, now - 1.0]
        # Joint 2: NaN
        buf[2] = [float("nan"), 2.0, 3.0, 0.9, 0.9, 0.9, now]
        # Rest: zero (will have stale timestamp 0)
        for i in range(3, JOINT_COUNT):
            buf[i] = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

        result = tracker.read_joints()
        assert result is not None
        assert len(result) == 1  # Only joint 0

    def test_no_shm_returns_none(self):
        """read_joints() returns None when shared memory is unavailable."""
        tracker = CameraTracker()
        assert tracker.read_joints() is None


class TestLifecycle:
    """Test start/stop lifecycle."""

    @patch("osc_tracking.camera_tracker.mp.Process")
    def test_start_creates_process(self, mock_proc_cls):
        tracker = CameraTracker()
        mock_proc = MagicMock()
        mock_proc.is_alive.return_value = False
        mock_proc_cls.return_value = mock_proc

        tracker.start()

        assert tracker._shm is not None
        mock_proc.start.assert_called_once()

        # Cleanup
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

    @patch("osc_tracking.camera_tracker.mp.Process")
    def test_double_start_is_noop(self, mock_proc_cls):
        tracker = CameraTracker()
        mock_proc = MagicMock()
        mock_proc.is_alive.return_value = True
        mock_proc_cls.return_value = mock_proc

        tracker.start()
        tracker.start()  # Should not create second process

        assert mock_proc_cls.call_count == 1
        tracker.stop()

    def test_is_alive_without_start(self):
        tracker = CameraTracker()
        assert tracker.is_alive is False


class TestMonotonicTimestamp:
    """_next_monotonic_ms guarantees strictly increasing ms values.

    MediaPipe VIDEO mode rejects non-monotonic timestamps, so the helper
    must bump past the previous frame even when a second frame arrives
    inside the same millisecond."""

    def test_advances_past_previous(self):
        prev = 1000
        ts = _next_monotonic_ms(prev)
        assert ts > prev

    def test_monotonic_under_same_ms(self, monkeypatch):
        """If two frames resolve to the same ms, the helper still advances."""
        monkeypatch.setattr(time, "monotonic", lambda: 1.000)
        a = _next_monotonic_ms(0)
        b = _next_monotonic_ms(a)
        assert b > a

    def test_tracks_wallclock_when_possible(self, monkeypatch):
        """When real time has advanced, use that (not a forced +1)."""
        monkeypatch.setattr(time, "monotonic", lambda: 5.500)
        ts = _next_monotonic_ms(100)
        assert ts >= 5500


class TestUniqueShmName:
    """_unique_shm_name makes names collision-resistant even if the old
    SHM-name format (PID only) would reuse stale state from a crashed process."""

    def test_includes_prefix(self):
        name = _unique_shm_name()
        assert name.startswith(SHM_NAME)

    def test_distinct_per_call(self):
        a = _unique_shm_name()
        b = _unique_shm_name()
        assert a != b


class TestStartCleansStaleShm:
    """start() must not bind to a leaked-from-previous-crash SHM.

    On POSIX, unlinking a stale SHM works but the shared buffer could still
    hold data from the crashed process if we naively ``create=False``. On
    Windows, the name remains bound until every open handle closes, so the
    only safe recourse on collision is to pick a fresh name. Either way,
    the tracker must never reuse an existing SHM it didn't create.
    """

    @patch("osc_tracking.camera_tracker.mp.Process")
    def test_start_picks_fresh_name_on_collision(
        self, mock_proc_cls, monkeypatch
    ):
        """When the first chosen name collides, start() retries and gets a
        different, freshly-created SHM — never the pre-existing one."""
        from osc_tracking import camera_tracker

        colliding_name = f"{SHM_NAME}_collision_{int(time.time_ns())}"

        names = iter([colliding_name, f"{colliding_name}_fresh"])
        monkeypatch.setattr(camera_tracker, "_unique_shm_name", lambda: next(names))

        leaked = shared_memory.SharedMemory(
            name=colliding_name, create=True, size=SHM_SIZE
        )
        try:
            buf = np.ndarray(
                (JOINT_COUNT, FLOATS_PER_JOINT),
                dtype=np.float64,
                buffer=leaked.buf,
            )
            buf.fill(-999.0)

            mock_proc = MagicMock()
            mock_proc.is_alive.return_value = False
            mock_proc_cls.return_value = mock_proc

            tracker = CameraTracker()
            try:
                tracker.start()
                assert tracker._shm is not None
                # Retry must have picked the second name, not rebound the leak.
                assert tracker._shm_name != colliding_name
                fresh = np.ndarray(
                    (JOINT_COUNT, FLOATS_PER_JOINT),
                    dtype=np.float64,
                    buffer=tracker._shm.buf,
                )
                assert not np.any(fresh == -999.0)
            finally:
                tracker.stop()
        finally:
            try:
                leaked.close()
                leaked.unlink()
            except FileNotFoundError:
                pass


class TestTornRead:
    """Test behavior under concurrent read/write scenarios."""

    @pytest.fixture
    def tracker_with_shm(self):
        tracker = CameraTracker()
        shm_name = f"test_torn_{id(tracker)}"
        shm = shared_memory.SharedMemory(name=shm_name, create=True, size=SHM_SIZE)
        tracker._shm = shm
        tracker._shm_name = shm_name
        yield tracker, shm
        try:
            shm.close()
            shm.unlink()
        except FileNotFoundError:
            pass

    def test_read_during_zero_buffer(self, tracker_with_shm):
        """Reading a zero-initialized buffer should return empty (stale timestamps)."""
        tracker, _shm = tracker_with_shm
        result = tracker.read_joints()
        assert result is not None
        assert len(result) == 0  # All timestamps are 0 (very stale)

    def test_buffer_copy_prevents_mutation(self, tracker_with_shm):
        """read_joints() should snapshot the buffer, not return a view."""
        tracker, shm = tracker_with_shm
        buf = np.ndarray(
            (JOINT_COUNT, FLOATS_PER_JOINT), dtype=np.float64, buffer=shm.buf
        )
        now = time.monotonic()
        buf[0] = [1.0, 2.0, 3.0, 0.9, 0.9, 0.9, now]

        result = tracker.read_joints()
        assert result is not None

        # Mutate shared memory after read
        buf[0] = [99.0, 99.0, 99.0, 0.1, 0.1, 0.1, now]

        # Original result should not change
        if JOINT_NAMES[0] in result:
            pos, _, _, _ = result[JOINT_NAMES[0]]
            assert pos[0] == pytest.approx(1.0)


class TestCamIndicesList:
    """N-camera config: cam_indices list replaces per-index fields.

    Back-compat: when cam_indices is omitted, it must derive from the
    legacy cam1_index / cam2_index fields. Forward: an explicit list is
    the preferred API, tolerant of 1 (mono) or 2+ (stereo) cameras.
    """

    def test_defaults_list_derived_from_legacy_fields(self):
        cfg = CameraConfig()
        assert cfg.cam_indices == [0, 1]

    def test_explicit_cam_indices_overrides_legacy_fields(self):
        cfg = CameraConfig(cam_indices=[3, 4])
        assert cfg.cam_indices == [3, 4]

    def test_mono_mode_single_camera(self):
        """A list of length 1 means monocular — valid, uses MediaPipe depth."""
        cfg = CameraConfig(cam_indices=[2])
        assert cfg.cam_indices == [2]
        assert cfg.camera_count == 1

    def test_stereo_two_cameras(self):
        cfg = CameraConfig(cam_indices=[0, 1])
        assert cfg.camera_count == 2

    def test_three_or_more_cameras_all_used(self):
        """3+ cameras are honored end-to-end via multi-view SVD-DLT.

        The old behaviour clipped to the first two and emitted a warning;
        the N-way worker now opens every index in ``cam_indices``.
        """
        cfg = CameraConfig(cam_indices=[0, 1, 2, 3])
        assert cfg.effective_cam_indices == [0, 1, 2, 3]
        assert cfg.camera_count == 4

    def test_zero_cameras_raises(self):
        with pytest.raises(ValueError):
            CameraConfig(cam_indices=[])

    def test_backcompat_legacy_fields_still_work(self):
        """Code that instantiates with cam1_index / cam2_index keeps working."""
        cfg = CameraConfig(cam1_index=5, cam2_index=6)
        assert cfg.cam_indices == [5, 6]
        assert cfg.effective_cam_indices == [5, 6]

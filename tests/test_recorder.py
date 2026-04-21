"""Tests for TrackingRecorder / TrackingPlayer round-trip."""

import json

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from osc_tracking.recorder import TrackingPlayer, TrackingRecorder


class TestRecorderLifecycle:
    def test_start_creates_file(self, tmp_path):
        rec = TrackingRecorder(output_dir=str(tmp_path))
        path = rec.start(filename="session.jsonl")
        try:
            assert path.exists()
            assert path.name == "session.jsonl"
        finally:
            rec.stop()

    def test_auto_filename_when_none(self, tmp_path):
        rec = TrackingRecorder(output_dir=str(tmp_path))
        path = rec.start()
        try:
            assert path.suffix == ".jsonl"
            assert path.name.startswith("recording_")
        finally:
            rec.stop()

    def test_record_frame_before_start_is_noop(self, tmp_path):
        rec = TrackingRecorder(output_dir=str(tmp_path))
        # Must not crash even though start() wasn't called
        rec.record_frame({}, "VISIBLE")
        assert rec.stop() == 0


class TestRecordRoundTrip:
    def test_roundtrip_preserves_joint_data(self, tmp_path):
        rec = TrackingRecorder(output_dir=str(tmp_path))
        path = rec.start(filename="rt.jsonl")

        joints = {
            "Hips": (np.array([1.0, 2.0, 3.0]), Rotation.identity(), 0.9),
            "Head": (np.array([0.5, 1.8, 0.1]), Rotation.from_euler("y", 90, degrees=True), 0.8),
        }
        rec.record_frame(joints, "VISIBLE")
        rec.record_frame(joints, "PARTIAL_OCCLUSION")
        assert rec.stop() == 2

        # Read back via TrackingPlayer
        player = TrackingPlayer(path)
        assert player.load() == 2

        frame1 = player.next_frame()
        assert frame1 is not None
        assert frame1["mode"] == "VISIBLE"
        assert "Hips" in frame1["joints"]
        assert frame1["joints"]["Hips"]["p"] == pytest.approx([1.0, 2.0, 3.0])
        assert frame1["joints"]["Hips"]["c"] == pytest.approx(0.9)

        frame2 = player.next_frame()
        assert frame2 is not None
        assert frame2["mode"] == "PARTIAL_OCCLUSION"
        assert player.next_frame() is None
        assert player.is_done is True

    def test_rotation_defaults_when_not_rotation(self, tmp_path):
        """Non-Rotation objects get a safe identity quaternion, not a crash."""
        rec = TrackingRecorder(output_dir=str(tmp_path))
        path = rec.start()
        rec.record_frame({"Hips": (np.zeros(3), None, 1.0)}, "VISIBLE")  # type: ignore[arg-type]
        rec.stop()

        with open(path, encoding="utf-8") as f:
            frame = json.loads(f.readline())
        assert frame["joints"]["Hips"]["r"] == [0, 0, 0, 1]


class TestPlayer:
    def test_reset_replays_from_start(self, tmp_path):
        rec = TrackingRecorder(output_dir=str(tmp_path))
        path = rec.start()
        rec.record_frame({"Hips": (np.zeros(3), Rotation.identity(), 1.0)}, "VISIBLE")
        rec.stop()

        player = TrackingPlayer(path)
        player.load()
        player.next_frame()
        assert player.is_done
        player.reset()
        assert player.current_index == 0
        assert not player.is_done


class TestPrivacyNotice:
    def test_start_logs_privacy_warning(self, tmp_path, caplog):
        """P5-1: recording captures absolute camera-frame positions, which
        can be reversed into room layout. Users should see that up front."""
        import logging

        rec = TrackingRecorder(output_dir=str(tmp_path))
        with caplog.at_level(logging.WARNING, logger="osc_tracking.recorder"):
            rec.start()
        rec.stop()

        warnings = [rec_ for rec_ in caplog.records if rec_.levelno >= logging.WARNING]
        assert warnings, "Expected at least one WARNING on recording start"
        joined = " ".join(r.message for r in warnings).lower()
        assert "位置" in joined or "position" in joined or "privacy" in joined.lower()

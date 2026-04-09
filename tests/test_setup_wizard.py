"""Tests for setup wizard check functions."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from osc_tracking.tools.setup_wizard import (
    STEPS,
    check_calibration,
    check_model,
)


class TestStepsStructure:
    def test_has_7_steps(self):
        assert len(STEPS) == 7

    def test_each_step_has_required_fields(self):
        for step in STEPS:
            assert "title" in step
            assert "description" in step
            assert "check" in step

    def test_first_step_is_slimetora(self):
        assert "SlimeTora" in STEPS[0]["title"]

    def test_last_step_is_launch(self):
        assert "起動" in STEPS[-1]["title"]


class TestCheckModel:
    def test_model_exists(self, tmp_path, monkeypatch):
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        model_file = model_dir / "pose_landmarker_heavy.task"
        model_file.write_bytes(b"x" * 1024)
        monkeypatch.chdir(tmp_path)
        ok, msg = check_model()
        assert ok is True
        assert "MB" in msg

    def test_model_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ok, msg = check_model()
        assert ok is False


class TestCheckCalibration:
    def test_calibration_exists(self, tmp_path, monkeypatch):
        calib_dir = tmp_path / "calibration_data"
        calib_dir.mkdir()
        (calib_dir / "stereo_calib.npz").write_bytes(b"data")
        monkeypatch.chdir(tmp_path)
        ok, msg = check_calibration()
        assert ok is True

    def test_calibration_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ok, msg = check_calibration()
        assert ok is False

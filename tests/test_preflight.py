"""Tests for startup preflight checks."""

from dataclasses import replace

import pytest

from osc_tracking.config import TrackingConfig
from osc_tracking.preflight import (
    PreflightIssue,
    check_calibration_file,
    check_model_file,
    check_osc_port,
    run_preflight_checks,
)


@pytest.fixture
def cfg(tmp_path):
    return TrackingConfig(
        cam1_index=0,
        cam2_index=1,
        calibration_file=str(tmp_path / "calib.npz"),
        model_path=str(tmp_path / "heavy.task"),
        model_path_lite=str(tmp_path / "lite.task"),
        osc_receive_host="127.0.0.1",
        osc_receive_port=0,  # OS picks a free port by default in tests
        osc_send_host="127.0.0.1",
        osc_send_port=9000,
    )


class TestModelFileCheck:
    def test_missing_both_models_is_error(self, cfg):
        issues = check_model_file(cfg.model_path, cfg.model_path_lite)
        assert any(i.severity == "error" and i.code == "missing_model" for i in issues)

    def test_lite_present_heavy_missing_is_ok(self, cfg, tmp_path):
        lite = tmp_path / "lite.task"
        lite.write_bytes(b"fake")
        issues = check_model_file(cfg.model_path, str(lite))
        assert not any(i.severity == "error" for i in issues)

    def test_heavy_present_is_ok(self, cfg, tmp_path):
        heavy = tmp_path / "heavy.task"
        heavy.write_bytes(b"fake")
        issues = check_model_file(str(heavy), cfg.model_path_lite)
        assert not any(i.severity == "error" for i in issues)


class TestCalibrationCheck:
    def test_missing_calib_is_warning(self, cfg):
        """Missing calibration is survivable (monocular fallback) — warn, don't block."""
        issues = check_calibration_file(cfg.calibration_file)
        assert any(i.severity == "warning" and i.code == "missing_calibration" for i in issues)

    def test_present_calib_is_ok(self, cfg, tmp_path):
        calib = tmp_path / "calib.npz"
        calib.write_bytes(b"fake")
        issues = check_calibration_file(str(calib))
        assert issues == []


class TestPortCheck:
    def test_free_port_is_ok(self):
        """Port 0 asks the OS for an ephemeral port — always free."""
        issues = check_osc_port("127.0.0.1", 0)
        assert issues == []

    def test_port_in_use_is_error(self):
        """If something's already bound there, we must surface it."""
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 0))
        busy_port = sock.getsockname()[1]
        try:
            issues = check_osc_port("127.0.0.1", busy_port)
            assert any(
                i.severity == "error" and i.code == "port_in_use"
                for i in issues
            ), issues
        finally:
            sock.close()


class TestRunPreflightChecks:
    def test_no_camera_skips_camera_checks(self, cfg):
        """--no-camera should not require model or calibration files."""
        issues = run_preflight_checks(cfg, no_camera=True)
        codes = {i.code for i in issues}
        assert "missing_model" not in codes
        assert "missing_calibration" not in codes

    def test_camera_mode_requires_model(self, cfg):
        issues = run_preflight_checks(cfg, no_camera=False)
        assert any(i.code == "missing_model" for i in issues)

    def test_has_errors(self, cfg):
        issues = run_preflight_checks(cfg, no_camera=False)
        assert PreflightIssue.has_errors(issues) is True

    def test_ok_state(self, cfg, tmp_path):
        """All required files present, port free → zero issues."""
        (tmp_path / "calib.npz").write_bytes(b"")
        (tmp_path / "heavy.task").write_bytes(b"")
        (tmp_path / "lite.task").write_bytes(b"")
        clean_cfg = replace(
            cfg,
            osc_receive_port=0,  # OS-picked free port
        )
        issues = run_preflight_checks(clean_cfg, no_camera=False)
        assert PreflightIssue.has_errors(issues) is False


class TestMessages:
    """Messages surface in Japanese with actionable fixes."""

    def test_missing_model_message_is_actionable(self, cfg):
        issues = check_model_file(cfg.model_path, cfg.model_path_lite)
        missing = [i for i in issues if i.code == "missing_model"][0]
        # User should know what command to run to fix it
        assert "download_model" in (missing.fix or "")

    def test_missing_calib_mentions_calibrate_tool(self, cfg):
        issues = check_calibration_file(cfg.calibration_file)
        calib = [i for i in issues if i.code == "missing_calibration"][0]
        assert "calibrate" in (calib.fix or "")

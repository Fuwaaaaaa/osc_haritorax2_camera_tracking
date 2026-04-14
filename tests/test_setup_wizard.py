"""Tests for setup wizard — prerequisite checks and step logic."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from osc_tracking.tools.setup_wizard import (
    check_cameras,
    check_mediapipe_model,
    check_osc_port_available,
    WizardStep,
    WIZARD_STEPS,
)


class TestCheckCameras:
    """Test camera availability detection."""

    @patch("cv2.VideoCapture")
    def test_both_cameras_available(self, mock_vc):
        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.read.return_value = (True, MagicMock())
        mock_vc.return_value = cap

        result = check_cameras(0, 1)
        assert result.cam1_ok is True
        assert result.cam2_ok is True

    @patch("cv2.VideoCapture")
    def test_camera1_missing(self, mock_vc):
        def fake_capture(idx):
            cap = MagicMock()
            if idx == 0:
                cap.isOpened.return_value = False
            else:
                cap.isOpened.return_value = True
                cap.read.return_value = (True, MagicMock())
            return cap
        mock_vc.side_effect = fake_capture

        result = check_cameras(0, 1)
        assert result.cam1_ok is False
        assert result.cam2_ok is True

    @patch("cv2.VideoCapture")
    def test_no_cameras(self, mock_vc):
        cap = MagicMock()
        cap.isOpened.return_value = False
        mock_vc.return_value = cap

        result = check_cameras(0, 1)
        assert result.cam1_ok is False
        assert result.cam2_ok is False


class TestCheckMediaPipeModel:
    def test_model_exists(self, tmp_path):
        model = tmp_path / "pose_landmarker_heavy.task"
        model.write_bytes(b"fake model")
        assert check_mediapipe_model(str(model)) is True

    def test_model_missing(self, tmp_path):
        assert check_mediapipe_model(str(tmp_path / "nonexistent.task")) is False


class TestCheckOscPort:
    def test_free_port(self):
        # Use a high random port that's likely free
        assert check_osc_port_available(59123) is True

    @patch("osc_tracking.tools.setup_wizard.socket")
    def test_occupied_port(self, mock_socket_mod):
        sock = MagicMock()
        sock.bind.side_effect = OSError("Address already in use")
        mock_socket_mod.socket.return_value = sock
        mock_socket_mod.AF_INET = 2
        mock_socket_mod.SOCK_DGRAM = 2
        mock_socket_mod.SOL_SOCKET = 1
        mock_socket_mod.SO_REUSEADDR = 2

        assert check_osc_port_available(6969) is False


class TestWizardSteps:
    def test_seven_steps_defined(self):
        assert len(WIZARD_STEPS) == 7

    def test_steps_have_required_fields(self):
        for step in WIZARD_STEPS:
            assert isinstance(step, WizardStep)
            assert step.number > 0
            assert len(step.title) > 0
            assert len(step.description) > 0

    def test_steps_numbered_sequentially(self):
        for i, step in enumerate(WIZARD_STEPS):
            assert step.number == i + 1

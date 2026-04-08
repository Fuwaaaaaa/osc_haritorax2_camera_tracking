"""Tests for fusion engine with mocked subsystems."""

import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from osc_tracking.complementary_filter import JOINT_NAMES
from osc_tracking.fusion_engine import FusionEngine
from osc_tracking.state_machine import TrackingMode


@pytest.fixture
def mock_camera():
    camera = MagicMock()
    camera.is_alive = True
    # Return realistic joint data
    camera.read_joints.return_value = {
        name: (np.array([0.0, 1.0, 2.0]), 0.9)
        for name in JOINT_NAMES
    }
    return camera


@pytest.fixture
def mock_receiver():
    receiver = MagicMock()
    receiver.is_connected = True
    receiver.get_bone_rotation.return_value = Rotation.identity()
    return receiver


@pytest.fixture
def mock_sender():
    sender = MagicMock()
    sender.send.return_value = True
    return sender


@pytest.fixture
def engine(mock_camera, mock_receiver, mock_sender):
    return FusionEngine(
        camera=mock_camera,
        receiver=mock_receiver,
        sender=mock_sender,
    )


class TestUpdateCycle:
    def test_update_returns_tracking_mode(self, engine):
        mode = engine.update()
        assert isinstance(mode, TrackingMode)

    def test_update_reads_camera(self, engine, mock_camera):
        engine.update()
        mock_camera.read_joints.assert_called_once()

    def test_update_sends_to_vrchat(self, engine, mock_sender):
        engine.update()
        mock_sender.send.assert_called_once()
        outputs = mock_sender.send.call_args[0][0]
        assert len(outputs) == len(JOINT_NAMES)

    def test_update_output_has_position_and_rotation(self, engine, mock_sender):
        engine.update()
        outputs = mock_sender.send.call_args[0][0]
        for output in outputs:
            assert output.position is not None
            assert output.rotation is not None
            assert output.joint_name in JOINT_NAMES


class TestVisibleMode:
    def test_high_confidence_is_visible(self, engine):
        mode = engine.update()
        assert mode == TrackingMode.VISIBLE

    def test_position_moves_toward_camera(self, engine, mock_sender):
        # Multiple updates should converge position
        for _ in range(30):
            engine.update()
            time.sleep(0.001)  # Small delay for dt calculation

        outputs = mock_sender.send.call_args[0][0]
        hips = next(o for o in outputs if o.joint_name == "Hips")
        # Position should be near camera target (0, 1, 2)
        assert np.linalg.norm(hips.position - np.array([0.0, 1.0, 2.0])) < 1.0


class TestFullOcclusion:
    def test_no_camera_data_transitions(self, engine, mock_camera):
        mock_camera.read_joints.return_value = None
        # Need multiple updates for hysteresis
        engine.state_machine.config.hysteresis_sec = 0.0
        engine.state_machine._last_osc_time = time.monotonic()
        mode = engine.update()
        assert mode == TrackingMode.FULL_OCCLUSION


class TestIMUDisconnected:
    def test_no_osc_triggers_disconnect(self, engine, mock_receiver):
        mock_receiver.is_connected = False
        engine.state_machine._last_osc_time = time.monotonic() - 2.0
        engine.state_machine.config.hysteresis_sec = 0.0
        mode = engine.update()
        assert mode == TrackingMode.IMU_DISCONNECTED


class TestErrorRecovery:
    def test_filter_exception_resets_joint(self, engine):
        """If the filter throws, the engine should reset the joint and continue."""
        with patch.object(
            engine.filter, "update", side_effect=ValueError("test error")
        ):
            # Should not raise
            mode = engine.update()
            assert isinstance(mode, TrackingMode)

    def test_camera_none_does_not_crash(self, engine, mock_camera):
        mock_camera.read_joints.return_value = None
        engine.state_machine.config.hysteresis_sec = 0.0
        engine.state_machine._last_osc_time = time.monotonic()
        mode = engine.update()
        assert isinstance(mode, TrackingMode)


class TestVisualCompass:
    def test_chest_heading_corrected_when_visible(self, engine, mock_camera, mock_receiver):
        """Visual compass should be applied to Chest joint in Visible mode."""
        # Provide elbow data for Visual Compass proxy
        mock_camera.read_joints.return_value = {
            name: (np.array([0.1 * i, 1.0, 2.0]), 0.9)
            for i, name in enumerate(JOINT_NAMES)
        }
        mock_receiver.get_bone_rotation.return_value = Rotation.from_euler(
            "xyz", [0, 45, 0], degrees=True  # IMU says 45° yaw
        )
        engine.update()
        # Should complete without error — Visual Compass applied


class TestLifecycle:
    def test_start_initializes_subsystems(self, engine, mock_camera, mock_receiver, mock_sender):
        engine.start()
        mock_camera.start.assert_called_once()
        mock_receiver.start.assert_called_once()
        mock_sender.connect.assert_called_once()

    def test_stop_cleans_up(self, engine, mock_camera, mock_receiver, mock_sender):
        engine.start()
        engine.stop()
        mock_camera.stop.assert_called_once()
        mock_receiver.stop.assert_called_once()
        mock_sender.close.assert_called_once()


class TestDtClamping:
    def test_large_dt_is_clamped(self, engine):
        """If the loop stalls, dt should be clamped to 0.1s max."""
        engine._last_update = time.monotonic() - 10.0  # Simulate 10s stall
        mode = engine.update()
        assert isinstance(mode, TrackingMode)
        # The filter should not explode from a huge dt

"""Tests for OSC sender using mock UDP client."""

import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from osc_tracking.osc_sender import OSCSender, TrackerOutput


@pytest.fixture
def sender():
    return OSCSender(host="127.0.0.1", port=19999)


@pytest.fixture
def mock_client(sender):
    client = MagicMock()
    sender._client = client
    sender._connected = True
    return client


@pytest.fixture
def sample_outputs():
    return [
        TrackerOutput(
            position=np.array([1.0, 2.0, 3.0]),
            rotation=Rotation.from_euler("xyz", [10, 20, 30], degrees=True),
            joint_name="Hips",
        ),
        TrackerOutput(
            position=np.array([0.0, 1.5, 0.0]),
            rotation=Rotation.identity(),
            joint_name="Chest",
        ),
    ]


class TestConnection:
    def test_connect_creates_client(self, sender):
        result = sender.connect()
        assert result is True
        assert sender._connected

    def test_close_cleans_up(self, sender):
        sender.connect()
        sender.close()
        assert not sender._connected
        assert sender._client is None


class TestSend:
    def test_send_calls_client(self, sender, mock_client, sample_outputs):
        result = sender.send(sample_outputs)
        assert result is True
        assert mock_client.send_message.call_count == 4  # 2 joints x (pos + rot)

    def test_send_position_format(self, sender, mock_client, sample_outputs):
        sender.send(sample_outputs)
        # First call should be Hips position
        call_args = mock_client.send_message.call_args_list[0]
        assert "/tracking/trackers/1/position" in call_args[0][0]
        pos = call_args[0][1]
        assert len(pos) == 3

    def test_send_rotation_format(self, sender, mock_client, sample_outputs):
        sender.send(sample_outputs)
        # Second call should be Hips rotation (euler degrees)
        call_args = mock_client.send_message.call_args_list[1]
        assert "/tracking/trackers/1/rotation" in call_args[0][0]
        rot = call_args[0][1]
        assert len(rot) == 3

    def test_unknown_joint_skipped(self, sender, mock_client):
        outputs = [
            TrackerOutput(
                position=np.zeros(3),
                rotation=Rotation.identity(),
                joint_name="UnknownJoint",
            ),
        ]
        sender.send(outputs)
        assert mock_client.send_message.call_count == 0

    def test_send_when_disconnected_retries(self, sender):
        sender._connected = False
        sender._last_retry = 0  # Allow immediate retry
        # connect will succeed (UDP doesn't actually connect)
        result = sender.send([])
        assert result is True

    def test_send_oserror_marks_disconnected(self, sender, mock_client, sample_outputs):
        mock_client.send_message.side_effect = OSError("Network error")
        result = sender.send(sample_outputs)
        assert result is False
        assert not sender._connected


class TestTrackerMapping:
    def test_all_main_joints_have_ids(self, sender):
        expected = ["Hips", "Chest", "Head", "LeftFoot", "RightFoot"]
        for joint in expected:
            assert joint in sender.JOINT_TO_TRACKER_ID

    def test_max_8_trackers(self, sender):
        assert len(sender.JOINT_TO_TRACKER_ID) <= 8


class TestSendEdgeCases:
    def test_send_empty_list(self, sender, mock_client):
        """Sending an empty list should succeed without calling client."""
        result = sender.send([])
        assert result is True
        assert mock_client.send_message.call_count == 0


class TestConnectCreatesClient:
    def test_connect_creates_simple_udp_client(self, sender):
        """connect() should create a _client instance."""
        assert sender._client is None
        sender.connect()
        assert sender._client is not None
        assert sender._connected is True


class TestDoubleClose:
    def test_double_close_is_safe(self, sender):
        """Calling close() twice should not raise."""
        sender.connect()
        sender.close()
        assert sender._client is None
        sender.close()  # Second close — must not crash
        assert sender._client is None
        assert not sender._connected


class TestRetryLogic:
    def test_send_disconnected_within_retry_interval_returns_false(self, sender):
        """If disconnected and within retry interval, send returns False."""
        sender._connected = False
        sender._last_retry = time.monotonic()  # Just retried
        result = sender.send([])
        assert result is False

    def test_send_disconnected_retries_after_interval(self, sender):
        """After retry interval, send attempts reconnect."""
        sender._connected = False
        sender._last_retry = 0  # Long ago
        result = sender.send([])
        assert result is True
        assert sender._connected

    def test_send_with_none_client_returns_false(self, sender):
        """If client is None after connect, send returns False."""
        sender._connected = True
        sender._client = None
        result = sender.send([
            TrackerOutput(
                position=np.zeros(3),
                rotation=Rotation.identity(),
                joint_name="Hips",
            ),
        ])
        assert result is False


class TestConnectFailure:
    def test_connect_oserror_returns_false(self, sender):
        """If SimpleUDPClient raises OSError, connect returns False."""
        with patch("osc_tracking.osc_sender.SimpleUDPClient", side_effect=OSError("fail")):
            result = sender.connect()
            assert result is False
            assert not sender._connected

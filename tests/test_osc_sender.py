"""Tests for OSC sender using mock UDP client."""

from unittest.mock import MagicMock

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

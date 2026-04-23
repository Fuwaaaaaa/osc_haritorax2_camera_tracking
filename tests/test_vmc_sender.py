"""Tests for the VMC Protocol sender.

Mocks the underlying ``SimpleUDPClient`` so we can assert the exact
OSC addresses and payloads emitted for a given joint dict, without
actually opening a UDP socket.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
from scipy.spatial.transform import Rotation

from osc_tracking.vmc_sender import JOINT_TO_VMC_BONE, VMCSender


def _sample_joints() -> dict:
    """Build a minimal joints dict covering one mapped + one unmapped joint."""
    return {
        "Hips": (np.array([1.0, 2.0, 3.0]), Rotation.identity()),
        "LeftKnee": (np.array([0.1, 0.2, 0.3]), Rotation.from_euler("y", 45, degrees=True)),
        "UnknownJoint": (np.array([0.0, 0.0, 0.0]), Rotation.identity()),
    }


def test_connect_creates_udp_client():
    sender = VMCSender(host="127.0.0.1", port=39539)
    with patch("osc_tracking.vmc_sender.SimpleUDPClient") as MockClient:
        MockClient.return_value = MagicMock()
        assert sender.connect() is True
        MockClient.assert_called_once_with("127.0.0.1", 39539)


def test_connect_returns_false_on_oserror():
    sender = VMCSender()
    with patch(
        "osc_tracking.vmc_sender.SimpleUDPClient", side_effect=OSError("bind failed")
    ):
        assert sender.connect() is False


def test_send_frame_without_connect_is_noop():
    """Calling send_frame before connect must not raise."""
    sender = VMCSender()
    sender.send_frame(_sample_joints())  # no _client — should silently return


def test_send_frame_emits_root_for_hips():
    sender = VMCSender()
    mock_client = MagicMock()
    sender._client = mock_client
    sender.send_frame(_sample_joints())

    root_calls = [
        c for c in mock_client.send_message.call_args_list
        if c.args[0] == "/VMC/Ext/Root/Pos"
    ]
    assert len(root_calls) == 1
    payload = root_calls[0].args[1]
    assert payload[0] == "Root"
    assert payload[1:4] == [1.0, 2.0, 3.0]  # hips position


def test_send_frame_emits_bone_pos_per_mapped_joint():
    sender = VMCSender()
    mock_client = MagicMock()
    sender._client = mock_client
    sender.send_frame(_sample_joints())

    bone_calls = [
        c for c in mock_client.send_message.call_args_list
        if c.args[0] == "/VMC/Ext/Bone/Pos"
    ]
    # All joints in _sample_joints are in JOINT_TO_VMC_BONE except "UnknownJoint"
    emitted_bones = {c.args[1][0] for c in bone_calls}
    expected_bones = {"Hips", "LeftLowerLeg"}  # from _sample_joints minus unknown
    assert expected_bones <= emitted_bones
    # Unknown joints must be skipped, not emitted as a bone.
    assert "UnknownJoint" not in emitted_bones


def test_send_frame_skips_unmapped_joint_names():
    sender = VMCSender()
    mock_client = MagicMock()
    sender._client = mock_client
    sender.send_frame({"NotRealJoint": (np.array([0, 0, 0]), Rotation.identity())})

    # Root is only emitted for Hips, so a dict without Hips and without any
    # mapped joint should produce only the availability ping.
    bone_calls = [
        c for c in mock_client.send_message.call_args_list
        if c.args[0] == "/VMC/Ext/Bone/Pos"
    ]
    assert bone_calls == []


def test_send_frame_sends_availability_signal():
    sender = VMCSender()
    mock_client = MagicMock()
    sender._client = mock_client
    sender.send_frame(_sample_joints())

    ok_calls = [
        c for c in mock_client.send_message.call_args_list
        if c.args[0] == "/VMC/Ext/OK"
    ]
    assert len(ok_calls) == 1
    assert ok_calls[0].args[1] == [1]


def test_send_frame_swallows_oserror():
    """Network blips should not bubble up to the fusion loop."""
    sender = VMCSender()
    sender._client = MagicMock()
    sender._client.send_message.side_effect = OSError("network down")
    # must not raise
    sender.send_frame(_sample_joints())


def test_joint_to_vmc_bone_mapping_covers_canonical_joints():
    """Sanity: every canonical skeleton bone (except Head, which VMC
    also calls Head) has a VMC mapping."""
    from osc_tracking.complementary_filter import JOINT_NAMES
    for name in JOINT_NAMES:
        assert name in JOINT_TO_VMC_BONE, f"{name} missing VMC mapping"


def test_close_clears_client_reference():
    sender = VMCSender()
    sender._client = MagicMock()
    sender.close()
    assert sender._client is None
    # Subsequent sends are noops, not crashes.
    sender.send_frame(_sample_joints())

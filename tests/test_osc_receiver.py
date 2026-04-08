"""Tests for OSC receiver using mock server."""

import time

import pytest
from scipy.spatial.transform import Rotation

from osc_tracking.osc_receiver import BoneData, OSCReceiver


@pytest.fixture
def receiver():
    r = OSCReceiver(host="127.0.0.1", port=19876)
    return r


class TestConnectionState:
    def test_not_connected_initially(self, receiver):
        assert not receiver.is_connected

    def test_seconds_since_last_receive_inf_initially(self, receiver):
        assert receiver.seconds_since_last_receive == float("inf")

    def test_connected_after_receive(self, receiver):
        receiver._last_receive_time = time.monotonic()
        assert receiver.is_connected

    def test_disconnected_after_timeout(self, receiver):
        receiver._last_receive_time = time.monotonic() - 2.0
        assert not receiver.is_connected


class TestBoneData:
    def test_get_bone_rotation_returns_none_for_unknown(self, receiver):
        assert receiver.get_bone_rotation("UnknownBone") is None

    def test_get_bone_rotation_returns_none_when_stale(self, receiver):
        receiver.bones["Hips"] = BoneData(
            rotation=Rotation.identity(),
            timestamp=time.monotonic() - 2.0,
        )
        assert receiver.get_bone_rotation("Hips") is None

    def test_get_bone_rotation_returns_rotation_when_fresh(self, receiver):
        rot = Rotation.from_euler("xyz", [10, 20, 30], degrees=True)
        receiver.bones["Hips"] = BoneData(
            rotation=rot,
            timestamp=time.monotonic(),
        )
        result = receiver.get_bone_rotation("Hips")
        assert result is not None


class TestHandleRotation:
    def test_valid_quaternion_parsed(self, receiver):
        receiver._handle_rotation(
            "/tracking/trackers/1/rotation", "Hips",
            0.0, 0.0, 0.0, 1.0,
        )
        assert receiver.bones["Hips"].timestamp > 0
        assert receiver.is_connected

    def test_short_args_ignored(self, receiver):
        old_ts = receiver.bones.get("Hips", BoneData()).timestamp
        receiver._handle_rotation(
            "/tracking/trackers/1/rotation", "Hips",
            0.0, 0.0,  # Only 2 args instead of 4
        )
        assert receiver.bones.get("Hips", BoneData()).timestamp == old_ts

    def test_nan_quaternion_ignored(self, receiver):
        receiver._handle_rotation(
            "/tracking/trackers/1/rotation", "Hips",
            float("nan"), 0.0, 0.0, 1.0,
        )
        # Should not update timestamp since NaN was rejected
        assert receiver.bones["Hips"].timestamp == 0.0

    def test_inf_quaternion_ignored(self, receiver):
        receiver._handle_rotation(
            "/tracking/trackers/1/rotation", "Hips",
            float("inf"), 0.0, 0.0, 1.0,
        )
        assert receiver.bones["Hips"].timestamp == 0.0


class TestServerLifecycle:
    def test_start_creates_server(self, receiver):
        receiver.start()
        assert receiver._running
        assert receiver._thread is not None
        assert receiver._thread.is_alive()
        receiver.stop()

    def test_stop_cleans_up(self, receiver):
        receiver.start()
        receiver.stop()
        assert not receiver._running
        assert receiver._thread is None

    def test_double_start_is_safe(self, receiver):
        receiver.start()
        receiver.start()  # Should not crash
        receiver.stop()

    def test_port_conflict_tries_alternative(self):
        """If port is taken, receiver tries port+1."""
        r1 = OSCReceiver(port=19877)
        r2 = OSCReceiver(port=19877)
        r1.start()
        try:
            r2.start()
            assert r2.port == 19878  # Should have incremented
        finally:
            r1.stop()
            r2.stop()


class TestDefaultAddresses:
    def test_all_8_trackers_mapped(self, receiver):
        assert len(receiver.bone_addresses) == 8

    def test_hips_mapped(self, receiver):
        assert "Hips" in receiver.bone_addresses.values()

    def test_chest_mapped(self, receiver):
        assert "Chest" in receiver.bone_addresses.values()

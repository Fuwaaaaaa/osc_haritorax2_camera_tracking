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
        """If port is taken, receiver tries port+1..+3."""
        import socket
        # Use a raw socket to block a port without OSC server overhead
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 19951))
        try:
            r = OSCReceiver(port=19951)
            r.start()
            assert r.port in (19952, 19953, 19954)
            r.stop()
        finally:
            sock.close()


class TestDefaultAddresses:
    def test_all_8_trackers_mapped(self, receiver):
        assert len(receiver.bone_addresses) == 8

    def test_hips_mapped(self, receiver):
        assert "Hips" in receiver.bone_addresses.values()

    def test_chest_mapped(self, receiver):
        assert "Chest" in receiver.bone_addresses.values()


class TestQuaternionNormalization:
    def test_quaternion_normalized(self, receiver):
        """Non-unit quaternion (2,0,0,0) should be normalized to (1,0,0,0)."""
        receiver._handle_rotation(
            "/tracking/trackers/1/rotation", "Hips",
            2.0, 0.0, 0.0, 0.0,
        )
        bone = receiver.bones["Hips"]
        assert bone.timestamp > 0
        quat = bone.rotation.as_quat()  # [x, y, z, w]
        assert abs(quat[0]) == pytest.approx(1.0, abs=1e-6)
        assert quat[1] == pytest.approx(0.0, abs=1e-6)
        assert quat[2] == pytest.approx(0.0, abs=1e-6)
        assert quat[3] == pytest.approx(0.0, abs=1e-6)

    def test_zero_quaternion_rejected(self, receiver):
        """Zero quaternion (0,0,0,0) should be rejected (norm < 1e-6)."""
        receiver._handle_rotation(
            "/tracking/trackers/1/rotation", "Hips",
            0.0, 0.0, 0.0, 0.0,
        )
        assert receiver.bones["Hips"].timestamp == 0.0

    def test_near_unit_quaternion_accepted(self, receiver):
        """Nearly-unit quaternion should be accepted and normalized."""
        receiver._handle_rotation(
            "/tracking/trackers/1/rotation", "Hips",
            0.999, 0.01, 0.01, 0.01,
        )
        bone = receiver.bones["Hips"]
        assert bone.timestamp > 0
        quat = bone.rotation.as_quat()
        norm = sum(q * q for q in quat) ** 0.5
        assert norm == pytest.approx(1.0, abs=1e-6)


class TestHandleUnknown:
    def test_handle_unknown_does_not_crash(self, receiver):
        """_handle_unknown should not raise any exception."""
        receiver._handle_unknown("/some/unknown/address", 1, 2, 3)
        receiver._handle_unknown("/another/addr")


class TestCustomBoneAddresses:
    def test_custom_bone_addresses(self):
        """Receiver initialized with custom addresses uses them."""
        custom = {"/custom/1": "MyBone", "/custom/2": "OtherBone"}
        r = OSCReceiver(host="127.0.0.1", port=19876, bone_addresses=custom)
        assert r.bone_addresses == custom
        assert "MyBone" in r.bones
        assert "OtherBone" in r.bones
        assert len(r.bones) == 2

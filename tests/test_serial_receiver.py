"""Unit tests for SerialReceiver.

These tests avoid any real serial I/O by injecting a fake Serial object
with scripted read payloads. Pure-function tests (frame parser) don't
need any mocks.

The test suite skips automatically if ``pyserial`` cannot be imported so
CI environments without the dependency stay green.
"""

from __future__ import annotations

import struct
import time
from unittest.mock import patch

import pytest

pytest.importorskip("serial", reason="pyserial not installed; skipping Serial receiver tests")

from osc_tracking import serial_receiver as serial_mod  # noqa: E402
from osc_tracking.serial_receiver import (  # noqa: E402
    FRAME_LENGTH,
    FRESHNESS_WINDOW_SEC,
    SYNC_BYTES,
    SerialReceiver,
    parse_frames,
)

# ---------- parse_frames: pure function tests ----------

def _build_frame(tracker_id: int, qx: int, qy: int, qz: int, qw: int) -> bytes:
    """Build a single well-formed frame for tests."""
    return SYNC_BYTES + bytes([tracker_id]) + struct.pack("<hhhh", qx, qy, qz, qw)


def test_parse_frames_extracts_single_frame():
    frame = _build_frame(tracker_id=3, qx=100, qy=-200, qz=300, qw=-400)
    frames, remainder = parse_frames(frame)
    assert len(frames) == 1
    tid, payload = frames[0]
    assert tid == 3
    assert payload == struct.pack("<hhhh", 100, -200, 300, -400)
    assert remainder == b""


def test_parse_frames_keeps_partial_frame_as_remainder():
    """A frame split across two reads must not be consumed until complete."""
    frame = _build_frame(tracker_id=1, qx=1, qy=2, qz=3, qw=4)
    partial = frame[: FRAME_LENGTH - 2]
    frames, remainder = parse_frames(partial)
    assert frames == []
    assert remainder == partial


def test_parse_frames_skips_garbage_before_sync():
    """Bytes preceding the sync pattern are dropped, not consumed as payload."""
    frame = _build_frame(tracker_id=2, qx=5, qy=6, qz=7, qw=8)
    buffer = b"\x00\x01\x99" + frame
    frames, remainder = parse_frames(buffer)
    assert len(frames) == 1
    tid, _ = frames[0]
    assert tid == 2
    assert remainder == b""


def test_parse_frames_extracts_multiple_frames_in_one_buffer():
    f1 = _build_frame(tracker_id=0, qx=1, qy=0, qz=0, qw=0)
    f2 = _build_frame(tracker_id=1, qx=0, qy=1, qz=0, qw=0)
    f3 = _build_frame(tracker_id=2, qx=0, qy=0, qz=1, qw=0)
    frames, remainder = parse_frames(f1 + f2 + f3)
    assert [tid for tid, _ in frames] == [0, 1, 2]
    assert remainder == b""


def test_parse_frames_returns_partial_trailing_frame_as_remainder():
    f1 = _build_frame(tracker_id=0, qx=1, qy=0, qz=0, qw=0)
    f2 = _build_frame(tracker_id=1, qx=0, qy=1, qz=0, qw=0)
    buffer = f1 + f2[:5]
    frames, remainder = parse_frames(buffer)
    assert len(frames) == 1
    # The trailing partial frame must start at sync bytes so the next
    # read can complete it — parser must not drop the sync prefix.
    assert remainder == f2[:5]


def test_parse_frames_handles_false_sync_inside_payload():
    """A 0xAA 0x55 appearing inside a quaternion must not desync the parser
    on subsequent frames."""
    # First frame embeds the sync pattern inside its quaternion bytes by
    # construction: qx low=0xAA, qx high=0x55 → int16LE = 0x55AA
    tricky = SYNC_BYTES + bytes([7]) + bytes([0xAA, 0x55, 0, 0, 0, 0, 0, 0])
    f2 = _build_frame(tracker_id=1, qx=1, qy=2, qz=3, qw=4)
    frames, remainder = parse_frames(tricky + f2)
    # We expect two frames: the tricky one and the following one. The
    # parser is length-framed (fixed FRAME_LENGTH), so an in-payload
    # sync pattern cannot mislead it.
    assert len(frames) == 2
    assert frames[0][0] == 7
    assert frames[1][0] == 1
    assert remainder == b""


# ---------- SerialReceiver init / bone name validation ----------

def test_init_warns_on_unknown_bone_name(caplog):
    caplog.set_level("WARNING", logger="osc_tracking.serial_receiver")
    SerialReceiver(port="COM_TEST", tracker_id_to_bone={0: "hips"})  # typo
    assert any("unknown bone name" in r.message.lower() for r in caplog.records)


def test_init_accepts_all_valid_bone_names(caplog):
    caplog.set_level("WARNING", logger="osc_tracking.serial_receiver")
    SerialReceiver(
        port="COM_TEST",
        tracker_id_to_bone={0: "Hips", 1: "Chest", 2: "LeftElbow"},
    )
    assert not any("unknown bone" in r.message.lower() for r in caplog.records)


# ---------- pull interface: freshness / staleness ----------

def _make_receiver() -> SerialReceiver:
    return SerialReceiver(
        port="COM_TEST",
        tracker_id_to_bone={0: "Hips", 1: "Chest"},
        reconnect_delay_sec=0.05,
    )


def test_get_bone_rotation_returns_none_when_never_received():
    r = _make_receiver()
    assert r.get_bone_rotation("Hips") is None


def test_get_bone_rotation_rejects_stale_sample():
    r = _make_receiver()
    from scipy.spatial.transform import Rotation

    from osc_tracking.serial_receiver import BoneData
    r.bones["Hips"] = BoneData(
        rotation=Rotation.identity(),
        timestamp=time.monotonic() - (FRESHNESS_WINDOW_SEC + 0.5),
    )
    assert r.get_bone_rotation("Hips") is None


def test_get_bone_rotation_returns_fresh_sample():
    r = _make_receiver()
    from scipy.spatial.transform import Rotation

    from osc_tracking.serial_receiver import BoneData
    r.bones["Hips"] = BoneData(rotation=Rotation.identity(), timestamp=time.monotonic())
    assert r.get_bone_rotation("Hips") is not None


def test_is_connected_tracks_last_receive():
    r = _make_receiver()
    assert r.is_connected is False
    r._last_receive_time = time.monotonic()
    assert r.is_connected is True
    r._last_receive_time = time.monotonic() - (FRESHNESS_WINDOW_SEC + 0.5)
    assert r.is_connected is False


def test_seconds_since_last_receive_returns_inf_before_first_sample():
    r = _make_receiver()
    assert r.seconds_since_last_receive == float("inf")


def test_handle_frame_updates_bone_and_timestamp():
    r = _make_receiver()
    payload = struct.pack("<hhhh", 10, 20, 30, 40)
    before = time.monotonic()
    r._handle_frame(tracker_id=0, payload=payload)
    assert r.bones["Hips"].timestamp >= before
    assert r.get_bone_rotation("Hips") is not None
    assert r.is_connected is True


def test_handle_frame_ignores_unmapped_tracker_id():
    """A tracker_id with no bone mapping should be silently dropped — no
    crash, no spurious bone creation."""
    r = _make_receiver()
    before_bones = dict(r.bones)
    payload = struct.pack("<hhhh", 1, 2, 3, 4)
    r._handle_frame(tracker_id=99, payload=payload)
    assert dict(r.bones) == before_bones
    assert r.is_connected is False


def test_handle_frame_ignores_malformed_payload():
    r = _make_receiver()
    r._handle_frame(tracker_id=0, payload=b"")
    assert r.bones["Hips"].timestamp == 0.0


# ---------- lifecycle: thread start/stop with pyserial mocked ----------

class _FakeSerial:
    """Minimal pyserial.Serial stand-in backed by a scripted byte stream."""

    def __init__(self, script: list[bytes] | None = None, fail_open: bool = False):
        if fail_open:
            import serial  # type: ignore[import-not-found]
            raise serial.SerialException("fake: port not found")
        self._script = list(script or [])
        self._closed = False
        self.is_open = True
        self.port = "COM_TEST"
        self.baudrate = 500000

    def read(self, size: int) -> bytes:
        if self._closed:
            return b""
        if not self._script:
            time.sleep(0.05)  # avoid busy loop in tests
            return b""
        chunk = self._script.pop(0)
        return chunk[:size]

    def close(self) -> None:
        self._closed = True
        self.is_open = False


def test_stop_is_idempotent_on_unstarted_receiver():
    r = _make_receiver()
    r.stop()  # must not raise
    assert r.is_connected is False


def test_start_stop_lifecycle_with_no_data(monkeypatch):
    """Receiver should start, poll an empty serial port, and exit on stop()."""
    monkeypatch.setattr(serial_mod, "RECONNECT_DELAY_SEC", 0.05)

    fake = _FakeSerial(script=[])
    with patch.object(serial_mod, "_open_serial", return_value=fake):
        r = _make_receiver()
        r.start()
        time.sleep(0.2)
        r.stop()
        assert r._thread is None or not r._thread.is_alive()


def test_start_is_idempotent(monkeypatch):
    monkeypatch.setattr(serial_mod, "RECONNECT_DELAY_SEC", 0.05)

    fake = _FakeSerial(script=[])
    with patch.object(serial_mod, "_open_serial", return_value=fake):
        r = _make_receiver()
        try:
            r.start()
            first_thread = r._thread
            r.start()
            assert r._thread is first_thread
        finally:
            r.stop()


def test_receives_frame_and_updates_bone(monkeypatch):
    """End-to-end: scripted serial bytes → bone rotation published."""
    monkeypatch.setattr(serial_mod, "RECONNECT_DELAY_SEC", 0.05)

    frame = _build_frame(tracker_id=0, qx=100, qy=-200, qz=300, qw=-400)
    fake = _FakeSerial(script=[frame])
    with patch.object(serial_mod, "_open_serial", return_value=fake):
        r = _make_receiver()
        r.start()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and r.get_bone_rotation("Hips") is None:
            time.sleep(0.05)
        try:
            assert r.get_bone_rotation("Hips") is not None
            assert r.is_connected is True
        finally:
            r.stop()


def test_reconnects_after_open_failure(monkeypatch):
    """If the first open raises, the loop should retry and eventually
    succeed when the port appears."""
    monkeypatch.setattr(serial_mod, "RECONNECT_DELAY_SEC", 0.05)

    import serial  # type: ignore[import-not-found]

    frame = _build_frame(tracker_id=0, qx=1, qy=2, qz=3, qw=4)
    call_count = {"n": 0}

    def _open(port, baudrate):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise serial.SerialException("port busy")
        return _FakeSerial(script=[frame])

    with patch.object(serial_mod, "_open_serial", side_effect=_open):
        r = _make_receiver()
        r.start()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and call_count["n"] < 2:
            time.sleep(0.05)
        try:
            assert call_count["n"] >= 2
        finally:
            r.stop()

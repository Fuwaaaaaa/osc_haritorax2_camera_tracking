"""Unit tests for BLEReceiver.

These tests avoid any real Bluetooth I/O by mocking the ``bleak`` package
where needed. Pure-function tests (decoder, freshness logic) don't need
mocks at all.

The test suite skips automatically if ``bleak`` cannot be imported so that
CI environments without a BLE stack (e.g. containers without BlueZ) stay
green without a core-dependency install.
"""

from __future__ import annotations

import asyncio
import struct
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("bleak", reason="bleak not installed; skipping BLE receiver tests")

from osc_tracking import ble_receiver as ble_mod  # noqa: E402
from osc_tracking.ble_receiver import (  # noqa: E402
    BLEReceiver,
    BoneData,
    FRESHNESS_WINDOW_SEC,
    ROTATION_SCALAR,
    decode_rotation,
)


# ---------- decode_rotation: pure function tests ----------

def test_decode_rotation_happy_path():
    """Plain int16 payload → correct quaternion, with Z/W sign flip."""
    # Raw values: x=100, y=-200, z=300, w=-400 (int16LE).
    # After scaling, z and w are negated:
    #   qx = 100 * s, qy = -200 * s, qz = -300 * s, qw = 400 * s
    payload = struct.pack("<hhhh", 100, -200, 300, -400)
    rot = decode_rotation(payload)
    assert rot is not None
    # scipy normalizes quaternions; compare the direction, not magnitude.
    q = rot.as_quat()  # (x, y, z, w)
    # Reconstruct the expected pre-normalization vector and normalize.
    import numpy as np
    expected = np.array([100, -200, -300, 400], dtype=float) * ROTATION_SCALAR
    expected = expected / np.linalg.norm(expected)
    # Quaternions q and -q are the same rotation; compare absolute dot product.
    assert abs(float(np.dot(q, expected))) == pytest.approx(1.0, abs=1e-6)


def test_decode_rotation_malformed_length():
    """Short payload should return None, not raise."""
    assert decode_rotation(b"") is None
    assert decode_rotation(b"\x00" * 7) is None  # one byte short


def test_decode_rotation_boundary_values():
    """int16 extremes should still produce a valid unit quaternion."""
    payload = struct.pack("<hhhh", 32767, -32768, 32767, -32768)
    rot = decode_rotation(payload)
    assert rot is not None
    # scipy-normalized quaternions are unit-length.
    import numpy as np
    q = rot.as_quat()
    assert np.linalg.norm(q) == pytest.approx(1.0, abs=1e-6)


def test_decode_rotation_zero_payload_rejected():
    """A zero-length raw quaternion is unrecoverable — receiver should reject it."""
    assert decode_rotation(b"\x00" * 8) is None


def test_decode_rotation_accepts_trailing_bytes():
    """Extra gravity/ankle bytes after the 8-byte quaternion are ignored."""
    payload = struct.pack("<hhhh", 10, 20, 30, 40) + b"\xff" * 20
    assert decode_rotation(payload) is not None


# ---------- pull interface: freshness / staleness ----------

def _make_receiver() -> BLEReceiver:
    return BLEReceiver(
        local_name_to_bone={"HaritoraX2-AAAA": "Hips", "HaritoraX2-BBBB": "Chest"},
        scan_timeout_sec=0.1,
    )


def test_get_bone_rotation_returns_none_when_never_received():
    r = _make_receiver()
    assert r.get_bone_rotation("Hips") is None


def test_get_bone_rotation_returns_fresh_sample():
    r = _make_receiver()
    now = time.monotonic()
    from scipy.spatial.transform import Rotation
    r.bones["Hips"] = BoneData(rotation=Rotation.identity(), timestamp=now)
    assert r.get_bone_rotation("Hips") is not None


def test_get_bone_rotation_rejects_stale_sample():
    r = _make_receiver()
    from scipy.spatial.transform import Rotation
    r.bones["Hips"] = BoneData(
        rotation=Rotation.identity(),
        timestamp=time.monotonic() - (FRESHNESS_WINDOW_SEC + 0.5),
    )
    assert r.get_bone_rotation("Hips") is None


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


def test_handle_sensor_data_updates_bone_and_timestamp():
    r = _make_receiver()
    payload = struct.pack("<hhhh", 10, 20, 30, 40)
    before = time.monotonic()
    r._handle_sensor_data(payload, "Hips")
    assert r.bones["Hips"].timestamp >= before
    assert r.get_bone_rotation("Hips") is not None
    assert r.is_connected is True


def test_handle_sensor_data_ignores_malformed_payload():
    r = _make_receiver()
    r._handle_sensor_data(b"", "Hips")
    assert r.bones["Hips"].timestamp == 0.0


# ---------- lifecycle: thread start/stop with bleak mocked ----------

def _patch_scanner_empty():
    """Patch BleakScanner.discover to return [] instantly."""
    async def _empty_discover(*_args, **_kwargs):
        return []

    scanner = MagicMock()
    scanner.discover = _empty_discover
    return patch.object(ble_mod, "asyncio", asyncio), patch(
        "bleak.BleakScanner", scanner
    )


def test_start_stop_lifecycle_with_no_devices(monkeypatch):
    """Receiver should start, find nothing, and exit cleanly on stop()."""
    # Short delays so the reconnect loop cycles fast.
    monkeypatch.setattr(ble_mod, "RECONNECT_DELAY_SEC", 0.05)

    async def _empty_discover(*_args, **_kwargs):
        return []

    with patch("bleak.BleakScanner.discover", side_effect=_empty_discover):
        r = _make_receiver()
        r.start()
        # Let the loop cycle at least once.
        time.sleep(0.3)
        r.stop()
        assert r._thread is None or not r._thread.is_alive()


def test_stop_is_idempotent_on_unstarted_receiver():
    r = _make_receiver()
    r.stop()  # must not raise
    assert r.is_connected is False


def test_start_is_idempotent():
    """Calling start() twice should not spawn a second thread."""
    async def _empty_discover(*_args, **_kwargs):
        return []

    with patch("bleak.BleakScanner.discover", side_effect=_empty_discover):
        r = _make_receiver()
        try:
            r.start()
            first_thread = r._thread
            r.start()
            assert r._thread is first_thread
        finally:
            r.stop()


# ---------- reconnect loop: mock a peripheral via monkeypatched sleep ----------

def test_sleep_interruptible_exits_when_running_flag_clears(monkeypatch):
    """_sleep_interruptible should return promptly after _running = False."""
    r = _make_receiver()
    r._running = True

    async def _drive():
        # Schedule a flip of _running in the background.
        async def _flip():
            await asyncio.sleep(0.05)
            r._running = False

        flip_task = asyncio.create_task(_flip())
        start = time.monotonic()
        await r._sleep_interruptible(5.0)
        elapsed = time.monotonic() - start
        await flip_task
        assert elapsed < 1.0, f"sleep_interruptible blocked for {elapsed:.2f}s"

    asyncio.run(_drive())

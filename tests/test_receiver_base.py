"""Tests for BaseIMUReceiver common lifecycle.

A minimal ``DummyReceiver`` subclass exercises the template methods so
the base class gets coverage independent of OSC / BLE / Serial
transports. Concrete receivers keep their own tests for their
transport-specific hooks.
"""

from __future__ import annotations

import logging
import threading
import time

import pytest
from scipy.spatial.transform import Rotation

from osc_tracking.receiver_base import (
    DEFAULT_FRESHNESS_WINDOW_SEC,
    BaseIMUReceiver,
    BoneData,
)
from osc_tracking.receiver_protocol import IMUReceiver


class DummyReceiver(BaseIMUReceiver):
    """Minimal concrete receiver for base-class tests.

    The loop just waits on the stop signal; a ``prepare_raises`` flag
    lets the test exercise the fail-fast behavior of
    ``_prepare_start``. A ``hang_on_stop`` flag lets the test cover
    the thread-join-timeout warning path.
    """

    def __init__(
        self,
        *,
        prepare_raises: Exception | None = None,
        hang_on_stop: bool = False,
        freshness_window_sec: float = DEFAULT_FRESHNESS_WINDOW_SEC,
    ) -> None:
        super().__init__(freshness_window_sec=freshness_window_sec)
        self._prepare_raises = prepare_raises
        self._hang_on_stop = hang_on_stop
        self.prepare_calls = 0
        self.stop_requested_calls = 0
        self._loop_started = threading.Event()

    def _thread_name(self) -> str:
        return "dummy-receiver"

    def _prepare_start(self) -> None:
        self.prepare_calls += 1
        if self._prepare_raises is not None:
            raise self._prepare_raises

    def _run_loop(self) -> None:
        self._loop_started.set()
        while self._running:
            time.sleep(0.01)
        if self._hang_on_stop:
            # Stay alive past the 2s join timeout to exercise the warning.
            time.sleep(3.0)


class TestPublicReadSurface:
    def test_is_connected_false_before_first_receive(self) -> None:
        r = DummyReceiver()
        assert r.is_connected is False
        assert r.seconds_since_last_receive == float("inf")

    def test_is_connected_true_within_freshness_window(self) -> None:
        r = DummyReceiver()
        r._last_receive_time = time.monotonic()
        assert r.is_connected is True

    def test_is_connected_false_after_freshness_window(self) -> None:
        r = DummyReceiver(freshness_window_sec=0.5)
        r._last_receive_time = time.monotonic() - 1.0
        assert r.is_connected is False

    def test_seconds_since_last_receive_monotonic(self) -> None:
        r = DummyReceiver()
        r._last_receive_time = time.monotonic() - 0.2
        assert 0.15 < r.seconds_since_last_receive < 0.3

    def test_get_bone_rotation_unknown_bone(self) -> None:
        r = DummyReceiver()
        assert r.get_bone_rotation("NonExistent") is None

    def test_get_bone_rotation_unreceived_returns_none(self) -> None:
        r = DummyReceiver()
        # Pre-populate with a default BoneData (timestamp 0.0) as
        # concrete receivers do — it must not leak as a live sample.
        r.bones["Hips"] = BoneData()
        assert r.get_bone_rotation("Hips") is None

    def test_get_bone_rotation_stale_returns_none(self) -> None:
        r = DummyReceiver(freshness_window_sec=0.5)
        r.bones["Hips"] = BoneData(
            rotation=Rotation.identity(),
            timestamp=time.monotonic() - 1.0,
        )
        assert r.get_bone_rotation("Hips") is None

    def test_get_bone_rotation_fresh_returns_rotation(self) -> None:
        r = DummyReceiver()
        rot = Rotation.from_euler("xyz", [0.1, 0.2, 0.3])
        r.bones["Hips"] = BoneData(rotation=rot, timestamp=time.monotonic())
        result = r.get_bone_rotation("Hips")
        assert result is not None
        assert result.as_quat() == pytest.approx(rot.as_quat())


class TestLifecycle:
    def test_start_is_idempotent(self) -> None:
        r = DummyReceiver()
        try:
            r.start()
            assert r._loop_started.wait(timeout=1.0)
            first_thread = r._thread
            r.start()
            assert r._thread is first_thread
            # Second start must not re-run preparation.
            assert r.prepare_calls == 1
        finally:
            r.stop()

    def test_stop_without_start_is_safe(self) -> None:
        r = DummyReceiver()
        r.stop()
        assert r._thread is None

    def test_start_then_stop_clears_thread(self) -> None:
        r = DummyReceiver()
        r.start()
        assert r._loop_started.wait(timeout=1.0)
        r.stop()
        assert r._thread is None
        assert r._running is False

    def test_prepare_failure_leaves_receiver_stopped(self) -> None:
        r = DummyReceiver(prepare_raises=OSError("port in use"))
        with pytest.raises(OSError, match="port in use"):
            r.start()
        # Fail-fast invariant: _running stays False, no thread lingers.
        assert r._running is False
        assert r._thread is None
        assert r.prepare_calls == 1

    def test_stop_warns_when_thread_exceeds_join_timeout(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        r = DummyReceiver(hang_on_stop=True)
        r.start()
        assert r._loop_started.wait(timeout=1.0)
        with caplog.at_level(logging.WARNING, logger="osc_tracking.receiver_base"):
            r.stop()
        assert any(
            "did not exit within 2s" in rec.message for rec in caplog.records
        )
        # Clean up the lingering thread so pytest doesn't complain.
        r._running = False

    def test_on_stop_requested_runs_before_join(self) -> None:
        r = DummyReceiver()
        r.start()
        assert r._loop_started.wait(timeout=1.0)
        r.stop()
        # DummyReceiver doesn't override _on_stop_requested, but the
        # default no-op must not raise and the join must still succeed.
        assert r._thread is None


class TestProtocolCompliance:
    def test_dummy_satisfies_imu_receiver_protocol(self) -> None:
        r = DummyReceiver()
        assert isinstance(r, IMUReceiver)


class TestWarnOnUnknownBones:
    """The shared helper that both BLE and Serial receivers use."""

    def test_silent_when_every_name_is_canonical(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="osc_tracking.receiver_base"):
            BaseIMUReceiver.warn_on_unknown_bones(["Hips", "Chest"], "Test")
        assert caplog.records == []

    def test_warns_listing_the_bad_names_and_transport(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="osc_tracking.receiver_base"):
            BaseIMUReceiver.warn_on_unknown_bones(["Hips", "leftfeet"], "BLE")
        assert any(
            "BLE" in rec.message and "leftfeet" in rec.message
            for rec in caplog.records
        )

    def test_empty_input_is_silent(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="osc_tracking.receiver_base"):
            BaseIMUReceiver.warn_on_unknown_bones([], "Serial")
        assert caplog.records == []

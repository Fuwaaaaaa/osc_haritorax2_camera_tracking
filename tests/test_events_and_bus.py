"""Domain event definitions + EventBus publish/subscribe tests."""

from __future__ import annotations

import time

import pytest

from osc_tracking.application.event_bus import EventBus
from osc_tracking.domain import Skeleton
from osc_tracking.domain.events import (
    DomainEvent,
    FrameProcessed,
    IMUDisconnected,
    IMUReconnected,
    OcclusionDetected,
    TrackingModeChanged,
)
from osc_tracking.state_machine import TrackingMode

# ---------- Event types ----------

def test_tracking_mode_changed_is_frozen():
    e = TrackingModeChanged(
        previous=TrackingMode.VISIBLE,
        current=TrackingMode.PARTIAL_OCCLUSION,
        timestamp=time.monotonic(),
    )
    with pytest.raises((AttributeError, TypeError)):
        e.current = TrackingMode.FULL_OCCLUSION  # type: ignore[misc]


def test_frame_processed_carries_snapshot():
    skel = Skeleton()
    skel.set_mode(TrackingMode.VISIBLE)
    skel.set_timestamp(1.0)
    e = FrameProcessed(timestamp=1.0, snapshot=skel.snapshot(), fps=30.0)
    assert e.snapshot.mode == TrackingMode.VISIBLE
    assert e.fps == 30.0


def test_all_event_types_implement_domain_event_base():
    for cls in (
        TrackingModeChanged,
        FrameProcessed,
        OcclusionDetected,
        IMUDisconnected,
        IMUReconnected,
    ):
        assert issubclass(cls, DomainEvent)


# ---------- EventBus ----------

def test_bus_delivers_event_to_subscriber():
    bus = EventBus()
    received: list[TrackingModeChanged] = []
    bus.subscribe(TrackingModeChanged, received.append)
    event = TrackingModeChanged(
        previous=TrackingMode.VISIBLE,
        current=TrackingMode.PARTIAL_OCCLUSION,
        timestamp=1.0,
    )
    bus.publish(event)
    assert received == [event]


def test_bus_routes_by_type():
    """A subscriber to TrackingModeChanged must NOT receive
    FrameProcessed events."""
    bus = EventBus()
    mode_events: list = []
    frame_events: list = []
    bus.subscribe(TrackingModeChanged, mode_events.append)
    bus.subscribe(FrameProcessed, frame_events.append)

    bus.publish(TrackingModeChanged(
        previous=TrackingMode.VISIBLE,
        current=TrackingMode.PARTIAL_OCCLUSION,
        timestamp=0.0,
    ))
    assert len(mode_events) == 1
    assert len(frame_events) == 0


def test_bus_supports_multiple_subscribers_per_event():
    bus = EventBus()
    a: list = []
    b: list = []
    bus.subscribe(IMUDisconnected, a.append)
    bus.subscribe(IMUDisconnected, b.append)
    bus.publish(IMUDisconnected(timestamp=0.0))
    assert len(a) == 1
    assert len(b) == 1


def test_bus_subscriber_exception_does_not_break_others():
    """A faulty subscriber must not take down other subscribers."""
    bus = EventBus()

    def boom(_e):
        raise RuntimeError("subscriber crashed")

    good: list = []
    bus.subscribe(IMUDisconnected, boom)
    bus.subscribe(IMUDisconnected, good.append)
    bus.publish(IMUDisconnected(timestamp=0.0))
    assert len(good) == 1


def test_bus_unsubscribe_stops_delivery():
    bus = EventBus()
    received: list = []
    handle = bus.subscribe(IMUReconnected, received.append)
    bus.publish(IMUReconnected(timestamp=0.0))
    assert len(received) == 1
    bus.unsubscribe(handle)
    bus.publish(IMUReconnected(timestamp=1.0))
    assert len(received) == 1  # unchanged


def test_bus_publish_with_no_subscribers_is_noop():
    bus = EventBus()
    # Must not raise
    bus.publish(IMUDisconnected(timestamp=0.0))

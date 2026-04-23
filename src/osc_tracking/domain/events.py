"""Domain events published by the fusion engine.

Events describe "something happened" — past tense, immutable, fire-and-forget.
Subscribers react (update a dashboard, send a notification, write a log)
without coupling back to the fusion engine.

All event types are ``@dataclass(frozen=True)`` and inherit from
:class:`DomainEvent` so the bus can type-dispatch and generic consumers
can hold a ``list[DomainEvent]``.
"""

from __future__ import annotations

from dataclasses import dataclass

from osc_tracking.domain.modes import TrackingMode
from osc_tracking.domain.skeleton import SkeletonSnapshot
from osc_tracking.domain.values import BoneId


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Common base. Subtypes add their own frozen fields."""

    timestamp: float


@dataclass(frozen=True, slots=True)
class TrackingModeChanged(DomainEvent):
    """Emitted when the state machine transitions between modes."""

    previous: TrackingMode
    current: TrackingMode


@dataclass(frozen=True, slots=True)
class FrameProcessed(DomainEvent):
    """Emitted once per fusion cycle with the latest aggregate snapshot."""

    snapshot: SkeletonSnapshot
    fps: float = 0.0


@dataclass(frozen=True, slots=True)
class OcclusionDetected(DomainEvent):
    """A joint that was visible last frame went occluded this frame."""

    bone: BoneId


@dataclass(frozen=True, slots=True)
class IMUDisconnected(DomainEvent):
    """IMU receiver stopped producing samples within the timeout window."""


@dataclass(frozen=True, slots=True)
class IMUReconnected(DomainEvent):
    """IMU receiver started producing samples again after a disconnect."""

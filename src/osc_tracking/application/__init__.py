"""Application layer — use-case orchestration.

The application layer wires domain types to infrastructure adapters
(receivers, cameras, persistence). It holds orchestration helpers like
:class:`EventBus` that are too coordination-heavy to live in the
domain layer but have no direct I/O themselves.
"""

from osc_tracking.application.event_bus import EventBus, Subscription

__all__ = ["EventBus", "Subscription"]

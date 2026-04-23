"""Synchronous in-process event bus.

The bus routes :class:`DomainEvent` subtypes to subscribers that registered
for that exact type. Dispatch is synchronous: :meth:`publish` returns only
after every subscriber has run. This keeps the fusion loop deterministic —
no event is dropped or reordered — and lets tests assert side effects
directly without sleeping for a queue drain.

Subscriber exceptions are logged and swallowed so one faulty handler does
not crash the fusion loop or prevent other handlers from running. The
original stack trace is preserved via ``logger.exception``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, TypeVar

from osc_tracking.domain.events import DomainEvent

logger = logging.getLogger(__name__)

E = TypeVar("E", bound=DomainEvent)
Handler = Callable[[E], None]


@dataclass(frozen=True, slots=True)
class Subscription:
    """Opaque token returned by :meth:`EventBus.subscribe`.

    Holding this handle lets a caller unsubscribe later. The fields are
    implementation details; do not rely on them externally.
    """

    event_type: type[DomainEvent]
    handler: Callable


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[type[DomainEvent], list[Callable]] = {}

    def subscribe(self, event_type: type[E], handler: Handler) -> Subscription:
        self._subscribers.setdefault(event_type, []).append(handler)
        return Subscription(event_type=event_type, handler=handler)

    def unsubscribe(self, subscription: Subscription) -> None:
        handlers = self._subscribers.get(subscription.event_type)
        if not handlers:
            return
        try:
            handlers.remove(subscription.handler)
        except ValueError:
            pass

    def publish(self, event: DomainEvent) -> None:
        """Deliver ``event`` to all subscribers of its exact type."""
        handlers = self._subscribers.get(type(event), [])
        for handler in list(handlers):  # list() so handlers can unsubscribe mid-dispatch
            try:
                handler(event)
            except Exception:
                logger.exception(
                    "EventBus subscriber %r raised while handling %s",
                    handler,
                    type(event).__name__,
                )

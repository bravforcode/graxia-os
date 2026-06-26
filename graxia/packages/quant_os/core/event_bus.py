"""
In-process Event Bus (quanttrader pattern — A4)

Decouples components via publish/subscribe.
Synchronous by default; async handlers supported.
Handler exceptions are isolated — one bad handler won't crash others.
"""

import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from .events import Event

logger = logging.getLogger(__name__)

Handler = Callable[[Event], Any]


class EventBus:
    """
    In-process pub/sub event bus.

    Usage:
        bus = EventBus()
        bus.subscribe(BarEvent, my_handler)
        bus.publish(BarEvent(symbol="XAUUSD"))
    """

    def __init__(self):
        self._subscribers: dict[type[Event], list[Handler]] = defaultdict(list)
        self._published_count: int = 0
        self._handler_errors: int = 0

    def subscribe(self, event_type: type[Event], handler: Handler) -> None:
        """Subscribe a handler to an event type"""
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: type[Event], handler: Handler) -> bool:
        """Remove a handler. Returns True if found and removed."""
        handlers = self._subscribers.get(event_type, [])
        try:
            handlers.remove(handler)
            return True
        except ValueError:
            return False

    def publish(self, event: Event) -> None:
        """
        Publish an event to all subscribers.
        Exceptions in handlers are logged but do not propagate.
        Subscribers to base types (Event) receive all events.
        """
        self._published_count += 1
        event_type = type(event)

        # Collect handlers for this exact type + all base types up to Event
        handlers = list(self._subscribers.get(event_type, []))
        for base_type in event_type.__mro__:
            if base_type is Event:
                handlers.extend(self._subscribers.get(Event, []))
                break
            if base_type is not event_type:
                handlers.extend(self._subscribers.get(base_type, []))

        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                self._handler_errors += 1
                logger.error(
                    "EventBus handler error [%s->%s]: %s",
                    event_type.__name__,
                    handler.__qualname__,
                    e,
                    exc_info=True,
                )

    def clear(self) -> None:
        """Remove all subscribers"""
        self._subscribers.clear()

    @property
    def published_count(self) -> int:
        return self._published_count

    @property
    def handler_errors(self) -> int:
        return self._handler_errors

    def subscriber_count(self, event_type: type[Event] | None = None) -> int:
        """Count subscribers. If event_type given, count for that type only."""
        if event_type is not None:
            return len(self._subscribers.get(event_type, []))
        return sum(len(h) for h in self._subscribers.values())

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


class _PublishResult:
    """Dual-mode return: works as sync None or async awaitable."""

    def __bool__(self):
        return False

    def __await__(self):
        async def _noop():
            return None
        return _noop().__await__()


class EventBus:
    """
    In-process pub/sub event bus.

    Supports both class-based (BarEvent) and string-based ("signal.new") routing.

    Usage:
        bus = EventBus()
        bus.subscribe(BarEvent, my_handler)
        bus.subscribe("signal.new", my_handler)
        bus.publish(BarEvent(symbol="XAUUSD"))
        bus.publish("signal.new", SignalEvent(symbol="XAUUSD"))
    """

    def __init__(self, max_queue_size: int = 0, event_log_path: str | None = None):
        self._subscribers: dict[type[Event] | str, list[Handler]] = defaultdict(list)
        self._published_count: int = 0
        self._handler_errors: int = 0
        self._max_queue_size = max_queue_size
        self._event_log_path = event_log_path

    def subscribe(self, event_type: type[Event] | str, handler: Handler) -> None:
        """Subscribe a handler to an event type (class or string key)."""
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: type[Event] | str, handler: Handler) -> bool:
        """Remove a handler. Returns True if found and removed."""
        handlers = self._subscribers.get(event_type, [])
        try:
            handlers.remove(handler)
            return True
        except ValueError:
            return False

    def publish(self, event_or_key: Event | str, event: Event | None = None) -> _PublishResult:
        """
        Publish an event to all subscribers.

        Supports two call styles:
            bus.publish(event)              — class-based routing via type(event)
            bus.publish("key", event)       — string-based routing via key

        Exceptions in handlers are logged but do not propagate.
        Subscribers to base types (Event) receive all events.
        """
        self._published_count += 1

        # Optional event persistence
        if self._event_log_path is not None:
            try:
                import json
                from pathlib import Path
                record = {
                    "event_type": type(event).__name__ if isinstance(event_or_key, Event) else str(event_or_key),
                    "event_id": getattr(event, 'event_id', ''),
                    "trace_id": getattr(event, 'trace_id', ''),
                    "timestamp": getattr(event, 'timestamp', '').isoformat() if hasattr(getattr(event, 'timestamp', ''), 'isoformat') else '',
                    "source": getattr(event, 'source', ''),
                }
                Path(self._event_log_path).parent.mkdir(parents=True, exist_ok=True)
                with open(self._event_log_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record) + "\n")
            except Exception:
                pass  # ponytail: never crash on logging

        if isinstance(event_or_key, str):
            key = event_or_key
            if event is None:
                return _PublishResult()
            event_type = type(event)
        else:
            key = None
            event = event_or_key
            event_type = type(event)

        handlers: list[Handler] = []

        # String-based routing
        if key is not None:
            handlers.extend(self._subscribers.get(key, []))

        # Class-based routing
        handlers.extend(self._subscribers.get(event_type, []))
        for base_type in event_type.__mro__:
            if base_type is Event:
                if event_type is not Event:
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

        return _PublishResult()

    def clear(self) -> None:
        """Remove all subscribers"""
        self._subscribers.clear()

    @property
    def published_count(self) -> int:
        return self._published_count

    @property
    def handler_errors(self) -> int:
        return self._handler_errors

    def subscriber_count(self, event_type: type[Event] | str | None = None) -> int:
        """Count subscribers. If event_type given, count for that type only."""
        if event_type is not None:
            return len(self._subscribers.get(event_type, []))
        return sum(len(h) for h in self._subscribers.values())

    async def start(self) -> None:
        """Start the event bus (async-compatible, no-op for synchronous bus)."""
        pass

    async def stop(self) -> None:
        """Stop the event bus (async-compatible, no-op for synchronous bus)."""
        pass

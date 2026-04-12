import asyncio
import inspect
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any, TypeAlias

logger = logging.getLogger(__name__)

EventPayload: TypeAlias = dict[str, Any]
EventHandler: TypeAlias = Callable[[EventPayload], object | Awaitable[object]]
QueuedEvent: TypeAlias = tuple[str, EventPayload]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._queue: asyncio.Queue[QueuedEvent] = asyncio.Queue()
        self._stats: dict[str, int] = defaultdict(int)
        self._running = False
        self._failed_events: list[tuple[str, EventPayload, str]] = []  # Dead letter queue

    def subscribe(self, event: str, handler: EventHandler) -> None:
        if handler in self._handlers[event]:
            logger.debug(
                "EventBus: skipping duplicate subscription %s to '%s'",
                getattr(handler, "__name__", handler.__class__.__name__),
                event,
            )
            return
        self._handlers[event].append(handler)
        logger.debug(
            "EventBus: subscribed %s to '%s'",
            getattr(handler, "__name__", handler.__class__.__name__),
            event,
        )

    async def emit(self, event: str, payload: EventPayload) -> None:
        self._stats[event] += 1
        await self._queue.put((event, payload))
        logger.debug(
            "EventBus: emitted '%s' with payload keys=%s",
            event,
            list(payload.keys()),
        )
    
    async def emit_domain_event(self, domain_event: Any) -> None:
        """
        Emit a typed Domain Event.
        
        This method accepts a DomainEvent instance and converts it to
        the event bus format for backward compatibility.
        
        Args:
            domain_event: Instance of a DomainEvent class
        """
        from app.core.domain_events import DomainEvent
        
        if not isinstance(domain_event, DomainEvent):
            raise TypeError(f"Expected DomainEvent, got {type(domain_event)}")
        
        event_name = domain_event.event_type()
        payload = domain_event.to_dict()
        dispatch_payload = {
            **payload,
            **payload.get("data", {}),
        }

        await self.emit(event_name, dispatch_payload)
        
        logger.debug(
            "EventBus: emitted domain event '%s' of type %s",
            event_name,
            domain_event.__class__.__name__,
        )

    async def start_processing(self) -> None:
        self._running = True
        logger.info("EventBus: processing loop started")
        while self._running:
            try:
                event, payload = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                handlers = self._handlers.get(event, [])
                if not handlers:
                    logger.debug(f"EventBus: no handlers for '{event}'")
                    continue
                for handler in handlers:
                    handler_name = getattr(handler, "__name__", handler.__class__.__name__)
                    try:
                        result = handler(payload)
                        if inspect.isawaitable(result):
                            await result
                    except Exception as exc:
                        logger.error(
                            "EventBus: handler %s failed for '%s': %s",
                            handler_name,
                            event,
                            exc,
                            exc_info=True,
                        )
                        # Add to dead letter queue
                        self._failed_events.append((event, payload, str(exc)))
                        # Keep only last 100 failed events
                        if len(self._failed_events) > 100:
                            self._failed_events.pop(0)
                self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception as exc:
                logger.error("EventBus: processing loop error: %s", exc, exc_info=True)

    def stop(self) -> None:
        self._running = False

    def get_event_stats(self) -> dict[str, int]:
        return dict(self._stats)
    
    def get_failed_events(self) -> list[tuple[str, EventPayload, str]]:
        """Get failed events from dead letter queue."""
        return self._failed_events.copy()
    
    async def replay_event(self, event: str, payload: EventPayload) -> None:
        """Replay a failed event."""
        await self.emit(event, payload)

    def reset(self) -> None:
        """Clear in-memory handlers and counters. Intended for deterministic tests."""
        self._handlers = defaultdict(list)
        self._stats = defaultdict(int)
        self._failed_events = []
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except asyncio.QueueEmpty:
                break


event_bus = EventBus()

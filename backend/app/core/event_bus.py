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
    def __init__(self, shutdown_timeout: int = 30, max_queue_size: int = 10000) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._queue: asyncio.Queue[QueuedEvent] = asyncio.Queue(maxsize=max_queue_size)
        self._stats: dict[str, int] = defaultdict(int)
        self._running = False
        self._failed_events: list[tuple[str, EventPayload, str]] = []  # Dead letter queue
        self._processing_tasks: set[asyncio.Task] = set()  # Track processing tasks
        self._shutdown_timeout: int = shutdown_timeout  # Configurable timeout
        self._max_queue_size: int = max_queue_size  # Maximum queue size for backpressure
        self._queue_full_count: int = 0  # Track how many times queue was full
        self._dropped_events: int = 0  # Track dropped events due to full queue

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

    async def emit(self, event: str, payload: EventPayload, timeout: float | None = 1.0) -> bool:
        """
        Emit an event to the queue with backpressure support.
        
        Args:
            event: Event name
            payload: Event payload
            timeout: Maximum time to wait if queue is full (None = wait forever)
        
        Returns:
            True if event was queued, False if queue was full and timeout expired
        
        Raises:
            asyncio.TimeoutError: If timeout is None and queue is full for too long
        """
        self._stats[event] += 1
        
        try:
            if timeout is None:
                # Wait forever (blocking backpressure)
                await self._queue.put((event, payload))
            else:
                # Wait with timeout (non-blocking backpressure)
                await asyncio.wait_for(self._queue.put((event, payload)), timeout=timeout)
            
            logger.debug(
                "EventBus: emitted '%s' with payload keys=%s (queue_size=%d/%d)",
                event,
                list(payload.keys()),
                self._queue.qsize(),
                self._max_queue_size,
            )
            return True
            
        except asyncio.TimeoutError:
            # Queue is full and timeout expired
            self._queue_full_count += 1
            self._dropped_events += 1
            logger.warning(
                "EventBus: queue full, dropped event '%s' (queue_size=%d/%d, total_dropped=%d)",
                event,
                self._queue.qsize(),
                self._max_queue_size,
                self._dropped_events,
            )
            return False
    
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

    async def _process_event(self, event: str, payload: EventPayload) -> None:
        """Process a single event by calling all registered handlers."""
        handlers = self._handlers.get(event, [])
        if not handlers:
            logger.debug(f"EventBus: no handlers for '{event}'")
            return
        
        for handler in handlers:
            handler_name = getattr(handler, "__name__", handler.__class__.__name__)
            try:
                result = handler(payload)
                if inspect.isawaitable(result):
                    await result
                logger.debug(f"EventBus: handler {handler_name} completed for '{event}'")
            except Exception as exc:
                logger.error(
                    "EventBus: handler %s failed for '%s': %s",
                    handler_name, event, exc, exc_info=True
                )
                self._failed_events.append((event, payload, str(exc)))
                if len(self._failed_events) > 100:
                    self._failed_events.pop(0)

    async def start_processing(self) -> None:
        """Start processing events from the queue with graceful shutdown support."""
        self._running = True
        self._processing_tasks = set()
        logger.info("EventBus: processing loop started")
        
        while self._running or not self._queue.empty():
            try:
                # If we're stopping and queue is empty, exit immediately
                if not self._running and self._queue.empty():
                    break

                # Wait for an item with a timeout to allow checking self._running
                try:
                    event, payload = await asyncio.wait_for(self._queue.get(), timeout=0.5)
                except (asyncio.TimeoutError, TimeoutError):
                    continue
                
                # Create task for processing
                task = asyncio.create_task(self._process_event(event, payload))
                self._processing_tasks.add(task)
                task.add_done_callback(self._processing_tasks.discard)
                
                # Mark queue item as done immediately after creating task
                self._queue.task_done()
                
            except RuntimeError as e:
                if "no running event loop" in str(e) or "Event loop is closed" in str(e):
                    logger.debug("EventBus: loop closing, stopping processing")
                    break
                logger.error("EventBus: runtime error: %s", e)
                break
            except Exception as exc:
                logger.error("EventBus: processing loop error: %s", exc, exc_info=True)
                if not self._running:
                    break
        
        # Wait for all processing tasks to complete
        if self._processing_tasks:
            logger.info(f"EventBus: waiting for {len(self._processing_tasks)} tasks to complete")
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._processing_tasks, return_exceptions=True),
                    timeout=self._shutdown_timeout
                )
            except (asyncio.TimeoutError, TimeoutError):
                logger.warning(
                    f"EventBus: shutdown timeout ({self._shutdown_timeout}s) exceeded, "
                    f"{len(self._processing_tasks)} tasks still running"
                )
                raise
        
        logger.info("EventBus: processing loop stopped gracefully")

    def stop(self) -> None:
        """Stop processing events (gracefully waits for current tasks)."""
        logger.info("EventBus: stop requested")
        self._running = False
        # Note: Actual waiting happens in start_processing() loop

    def get_event_stats(self) -> dict[str, int]:
        return dict(self._stats)
    
    def get_queue_metrics(self) -> dict[str, int]:
        """Get queue metrics for monitoring."""
        return {
            "queue_size": self._queue.qsize(),
            "max_queue_size": self._max_queue_size,
            "queue_full_count": self._queue_full_count,
            "dropped_events": self._dropped_events,
            "queue_utilization_percent": int((self._queue.qsize() / self._max_queue_size) * 100),
        }
    
    def get_failed_events(self) -> list[tuple[str, EventPayload, str]]:
        """Get failed events from dead letter queue."""
        return self._failed_events.copy()
    
    async def replay_event(self, event: str, payload: EventPayload) -> None:
        """Replay a failed event."""
        await self.emit(event, payload)

    def reset(self) -> None:
        """
        Clear in-memory handlers and counters. Intended for deterministic tests.
        
        SECURITY: This method should NEVER be called in production as it will:
        - Clear all event handlers (breaking event processing)
        - Clear event statistics (losing monitoring data)
        - Clear failed events queue (losing error tracking)
        - Reset the event queue (dropping pending events)
        
        Raises:
            RuntimeError: If called in production environment
        """
        # Production guard: Prevent accidental reset in production
        try:
            from app.config import settings
            if settings.APP_ENV.lower() == "production":
                raise RuntimeError(
                    "EventBus.reset() cannot be called in production environment. "
                    "This method is intended for testing only and will clear all "
                    "event handlers, statistics, and pending events."
                )
        except ImportError:
            # If settings not available, allow reset (e.g., during testing)
            pass
        
        logger.warning(
            "EventBus.reset() called - clearing all handlers, stats, and queue. "
            "This should only happen in tests!"
        )
        
        self._handlers = defaultdict(list)
        self._stats = defaultdict(int)
        self._failed_events = []
        self._queue = asyncio.Queue(maxsize=self._max_queue_size)
        self._queue_full_count = 0
        self._dropped_events = 0


def _create_global_event_bus() -> EventBus:
    """Create the global event bus instance with configuration from settings."""
    try:
        from app.config import settings
        return EventBus(
            shutdown_timeout=settings.EVENT_BUS_SHUTDOWN_TIMEOUT,
            max_queue_size=settings.EVENT_BUS_MAX_QUEUE_SIZE,
        )
    except Exception:
        # Fallback to default if settings not available (e.g., during import)
        return EventBus()


event_bus = _create_global_event_bus()

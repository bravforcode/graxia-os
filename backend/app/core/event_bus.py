import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._queue: asyncio.Queue = asyncio.Queue()
        self._stats: dict[str, int] = defaultdict(int)
        self._running = False

    def subscribe(self, event: str, handler: Callable) -> None:
        self._handlers[event].append(handler)
        logger.debug(f"EventBus: subscribed {handler.__name__} to '{event}'")

    async def emit(self, event: str, payload: dict) -> None:
        self._stats[event] += 1
        await self._queue.put((event, payload))
        logger.debug(f"EventBus: emitted '{event}' with payload keys={list(payload.keys())}")

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
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(payload)
                        else:
                            handler(payload)
                    except Exception as e:
                        logger.error(f"EventBus: handler {handler.__name__} failed for '{event}': {e}", exc_info=True)
                self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"EventBus: processing loop error: {e}", exc_info=True)

    def stop(self) -> None:
        self._running = False

    def get_event_stats(self) -> dict:
        return dict(self._stats)


event_bus = EventBus()

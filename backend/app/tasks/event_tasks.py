import asyncio
import logging

from app.core.bootstrap import wire_event_handlers
from app.core.event_bus import event_bus
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# Ensure handlers are wired in the worker process
wire_event_handlers()

@celery_app.task(name="app.tasks.event_tasks.process_event_bg")
def process_event_bg(event_name: str, payload: dict):
    """
    Celery task to process an event asynchronously in a worker.
    """
    logger.info(f"Background processing event: {event_name}")
    
    # We need to run the async handlers in a synchronous Celery task
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # This shouldn't happen in a standard Celery worker unless using gevent/eventlet
        asyncio.create_task(_handle_event(event_name, payload))
    else:
        loop.run_until_complete(_handle_event(event_name, payload))

async def _handle_event(event_name: str, payload: dict):
    handlers = event_bus._handlers.get(event_name, [])
    for handler in handlers:
        try:
            result = handler(payload)
            if asyncio.iscoroutine(result) or hasattr(result, "__await__"):
                await result
        except Exception as e:
            logger.error(f"Error in background event handler for {event_name}: {e}", exc_info=True)

"""
Event Bus API

Provides endpoints for monitoring and managing event bus operations.
"""
import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from app.core.event_bus import event_bus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.get("/stats")
async def get_event_stats():
    """
    Get event statistics.
    
    Returns:
        Event emission counts by event type
    """
    stats = event_bus.get_event_stats()
    return {
        "total_events": sum(stats.values()),
        "by_type": stats
    }


@router.get("/failed")
async def get_failed_events():
    """
    Get failed events from dead letter queue.
    
    Returns:
        List of failed events with error details
    """
    failed = event_bus.get_failed_events()
    return {
        "total": len(failed),
        "events": [
            {
                "index": idx,
                "event": event,
                "payload": payload,
                "error": error
            }
            for idx, (event, payload, error) in enumerate(failed)
        ]
    }


@router.post("/replay/{index}")
async def replay_event(index: int):
    """
    Replay a failed event by index.
    
    Args:
        index: Index of the failed event in the dead letter queue
    
    Returns:
        Success status and event details
    """
    failed = event_bus.get_failed_events()
    
    if index < 0 or index >= len(failed):
        raise HTTPException(status_code=404, detail="Event not found")
    
    event, payload, error = failed[index]
    
    try:
        await event_bus.replay_event(event, payload)
        logger.info(f"Replayed event: {event} (index {index})")
        return {
            "success": True,
            "event": event,
            "payload": payload,
            "previous_error": error
        }
    except Exception as e:
        logger.error(f"Failed to replay event {event}: {e}")
        raise HTTPException(status_code=500, detail=f"Replay failed: {str(e)}")


@router.delete("/failed/{index}")
async def remove_failed_event(index: int):
    """
    Remove a failed event from the dead letter queue.
    
    Args:
        index: Index of the failed event to remove
    
    Returns:
        Success status
    """
    failed = event_bus.get_failed_events()
    
    if index < 0 or index >= len(failed):
        raise HTTPException(status_code=404, detail="Event not found")
    
    # Remove from internal list
    event_bus._failed_events.pop(index)
    
    return {
        "success": True,
        "message": f"Removed failed event at index {index}"
    }


@router.delete("/failed")
async def clear_failed_events():
    """
    Clear all failed events from the dead letter queue.
    
    Returns:
        Number of events cleared
    """
    count = len(event_bus._failed_events)
    event_bus._failed_events.clear()
    
    logger.info(f"Cleared {count} failed events")
    
    return {
        "success": True,
        "cleared": count
    }


@router.get("/health")
async def get_event_bus_health():
    """
    Get event bus health status.
    
    Returns:
        Health metrics including queue size and failed events
    """
    stats = event_bus.get_event_stats()
    failed = event_bus.get_failed_events()
    
    return {
        "status": "healthy" if len(failed) < 10 else "degraded",
        "running": event_bus._running,
        "queue_size": event_bus._queue.qsize(),
        "total_events_processed": sum(stats.values()),
        "failed_events": len(failed),
        "event_types": len(stats)
    }

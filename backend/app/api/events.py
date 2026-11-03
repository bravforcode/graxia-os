"""
Event Bus API

Provides endpoints for monitoring and managing event bus operations.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException

from app.auth.context import AuthContext
from app.auth.dependencies import require_organization
from app.core.event_bus import DeliverySuccessReplayError, event_bus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.get("/stats")
async def get_event_stats(
    auth: AuthContext = Depends(require_organization),
):
    """
    Get event statistics.
    
    Returns:
        Event emission counts by event type
    """
    stats = event_bus.get_event_stats_for_organization(auth.organization_id)
    return {
        "total_events": sum(stats.values()),
        "by_type": stats
    }


@router.get("/failed")
async def get_failed_events(
    auth: AuthContext = Depends(require_organization),
):
    """
    Get failed events from dead letter queue.
    
    Returns:
        List of failed events with error details
    """
    failed = event_bus.get_failed_events_for_organization(auth.organization_id)
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
async def replay_event(
    index: int,
    auth: AuthContext = Depends(require_organization),
):
    """
    Replay a failed event by index.
    
    Args:
        index: Index of the failed event in the dead letter queue
    
    Returns:
        Success status and event details
    """
    failed = event_bus.get_failed_events_for_organization(auth.organization_id)
    
    if index < 0 or index >= len(failed):
        raise HTTPException(status_code=404, detail="Event not found")
    
    event, payload, error = failed[index]
    
    try:
        await event_bus.replay_event(event, payload, auth_context=auth)
        logger.info(f"Replayed event: {event} (index {index})")
        return {
            "success": True,
            "event": event,
            "payload": payload,
            "previous_error": error
        }
    except DeliverySuccessReplayError:
        raise HTTPException(status_code=409, detail="Delivery success events cannot be replayed")
    except Exception as e:
        logger.error(f"Failed to replay event {event}: {e}")
        raise HTTPException(status_code=500, detail=f"Replay failed: {str(e)}")


@router.delete("/failed/{index}")
async def remove_failed_event(
    index: int,
    auth: AuthContext = Depends(require_organization),
):
    """
    Remove a failed event from the dead letter queue.
    
    Args:
        index: Index of the failed event to remove
    
    Returns:
        Success status
    """
    if not event_bus.remove_failed_event_for_organization(index, auth.organization_id):
        raise HTTPException(status_code=404, detail="Event not found")
    
    return {
        "success": True,
        "message": f"Removed failed event at index {index}"
    }


@router.delete("/failed")
async def clear_failed_events(
    auth: AuthContext = Depends(require_organization),
):
    """
    Clear all failed events from the dead letter queue.
    
    Returns:
        Number of events cleared
    """
    count = event_bus.clear_failed_events_for_organization(auth.organization_id)
    
    logger.info(f"Cleared {count} failed events")
    
    return {
        "success": True,
        "cleared": count
    }


@router.get("/health")
async def get_event_bus_health(
    auth: AuthContext = Depends(require_organization),
):
    """
    Get event bus health status.
    
    Returns:
        Health status and this tenant's failed event count
    """
    failed = event_bus.get_failed_events_for_organization(auth.organization_id)
    
    return {
        "status": "healthy" if len(failed) < 10 else "degraded",
        "failed_events": len(failed),
    }

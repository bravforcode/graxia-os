"""
Outbox Event API Routes
CEO dashboard endpoints for transactional outbox visibility
"""
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.db import get_db_session
from ....packages.revenue_os.models import OutboxEvent
from ....packages.revenue_os.schemas.outbox_schemas import (
    OutboxEventResponse,
    OutboxEventList,
    OutboxStats,
    OutboxRetryRequest,
)
from ..dependencies import require_admin_api_key

router = APIRouter(prefix="/outbox", tags=["Outbox Events"])


@router.get(
    "/events",
    response_model=OutboxEventList,
    summary="List outbox events",
    description="Query transactional outbox events with filters",
)
async def list_outbox_events(
    aggregate_type: Optional[str] = Query(None, description="Filter by aggregate type (order, lead, campaign)"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    processed: Optional[bool] = Query(None, description="Filter by processed status"),
    retry_count_max: Optional[int] = Query(None, ge=0, description="Max retry count for failed events"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    _: str = Depends(require_admin_api_key),
):
    """Query outbox events with filters."""
    query = select(OutboxEvent)
    
    conditions = []
    if aggregate_type:
        conditions.append(OutboxEvent.aggregate_type == aggregate_type)
    if event_type:
        conditions.append(OutboxEvent.event_type == event_type)
    if processed is not None:
        conditions.append(OutboxEvent.processed == processed)
    if retry_count_max is not None:
        conditions.append(OutboxEvent.retry_count <= retry_count_max)
    
    if conditions:
        query = query.where(and_(*conditions))
    
    # Get total
    count_result = await db.execute(query)
    total = len(count_result.scalars().all())
    
    # Apply pagination
    query = query.order_by(desc(OutboxEvent.created_at)).offset(offset).limit(limit)
    result = await db.execute(query)
    events = result.scalars().all()
    
    return {
        "items": events,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get(
    "/events/{event_id}",
    response_model=OutboxEventResponse,
    summary="Get outbox event by ID",
)
async def get_outbox_event(
    event_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: str = Depends(require_admin_api_key),
):
    """Get a specific outbox event."""
    result = await db.execute(
        select(OutboxEvent).where(OutboxEvent.id == event_id)
    )
    event = result.scalar_one_or_none()
    
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Outbox event {event_id} not found",
        )
    
    return event


@router.get(
    "/stats",
    response_model=OutboxStats,
    summary="Get outbox statistics",
    description="Statistics about outbox event processing",
)
async def get_outbox_stats(
    db: AsyncSession = Depends(get_db_session),
    _: str = Depends(require_admin_api_key),
):
    """Get outbox event statistics."""
    # Total counts
    total_result = await db.execute(select(func.count(OutboxEvent.id)))
    total = total_result.scalar() or 0
    
    # Processed counts
    processed_result = await db.execute(
        select(func.count(OutboxEvent.id))
        .where(OutboxEvent.processed == True)
    )
    processed = processed_result.scalar() or 0
    
    # Unprocessed counts
    unprocessed = total - processed
    
    # Failed (retry_count >= 3)
    failed_result = await db.execute(
        select(func.count(OutboxEvent.id))
        .where(OutboxEvent.retry_count >= 3)
    )
    failed = failed_result.scalar() or 0
    
    # By aggregate type
    by_aggregate_result = await db.execute(
        select(OutboxEvent.aggregate_type, func.count(OutboxEvent.id))
        .group_by(OutboxEvent.aggregate_type)
    )
    by_aggregate = {k: v for k, v in by_aggregate_result.all()}
    
    # By event type
    by_event_result = await db.execute(
        select(OutboxEvent.event_type, func.count(OutboxEvent.id))
        .group_by(OutboxEvent.event_type)
    )
    by_event = {k: v for k, v in by_event_result.all()}
    
    # Average processing time (for processed events)
    avg_time_result = await db.execute(
        select(func.avg(
            func.extract('epoch', OutboxEvent.processed_at) - 
            func.extract('epoch', OutboxEvent.created_at)
        ))
        .where(OutboxEvent.processed == True)
    )
    avg_processing_seconds = avg_time_result.scalar()
    
    return {
        "total": total,
        "processed": processed,
        "unprocessed": unprocessed,
        "failed": failed,
        "by_aggregate_type": by_aggregate,
        "by_event_type": by_event,
        "avg_processing_seconds": avg_processing_seconds,
    }


@router.post(
    "/events/{event_id}/retry",
    response_model=OutboxEventResponse,
    summary="Retry failed outbox event",
    description="Reset retry count and mark for reprocessing",
)
async def retry_outbox_event(
    event_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: str = Depends(require_admin_api_key),
):
    """Retry a failed outbox event."""
    result = await db.execute(
        select(OutboxEvent).where(OutboxEvent.id == event_id)
    )
    event = result.scalar_one_or_none()
    
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Outbox event {event_id} not found",
        )
    
    # Reset for retry
    event.retry_count = 0
    event.last_error = None
    event.processed = False
    event.processed_at = None
    
    await db.commit()
    await db.refresh(event)
    
    return event


@router.get(
    "/failed",
    response_model=OutboxEventList,
    summary="Get failed outbox events",
    description="Events that exceeded max retry count",
)
async def get_failed_events(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    _: str = Depends(require_admin_api_key),
):
    """Get outbox events that failed (retry_count >= 3)."""
    query = (
        select(OutboxEvent)
        .where(OutboxEvent.retry_count >= 3)
        .order_by(desc(OutboxEvent.created_at))
    )
    
    # Get total
    count_result = await db.execute(query)
    total = len(count_result.scalars().all())
    
    # Apply pagination
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    events = result.scalars().all()
    
    return {
        "items": events,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get(
    "/pending",
    response_model=OutboxEventList,
    summary="Get pending outbox events",
    description="Events not yet processed",
)
async def get_pending_events(
    max_retry_count: int = Query(2, ge=0, description="Max retry count to include"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    _: str = Depends(require_admin_api_key),
):
    """Get unprocessed outbox events."""
    query = (
        select(OutboxEvent)
        .where(
            and_(
                OutboxEvent.processed == False,
                OutboxEvent.retry_count <= max_retry_count,
            )
        )
        .order_by(asc(OutboxEvent.created_at))
    )
    
    # Get total
    count_result = await db.execute(query)
    total = len(count_result.scalars().all())
    
    # Apply pagination
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    events = result.scalars().all()
    
    return {
        "items": events,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post(
    "/cleanup",
    summary="Clean up old processed events",
    description="Delete processed events older than retention days",
)
async def cleanup_old_events(
    retention_days: int = Query(30, ge=1, description="Keep events from last N days"),
    db: AsyncSession = Depends(get_db_session),
    _: str = Depends(require_admin_api_key),
):
    """Clean up old processed outbox events."""
    from datetime import timedelta
    
    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
    
    # Delete old processed events
    from sqlalchemy import delete
    
    result = await db.execute(
        delete(OutboxEvent)
        .where(
            and_(
                OutboxEvent.processed == True,
                OutboxEvent.processed_at < cutoff_date,
            )
        )
    )
    await db.commit()
    
    return {
        "deleted_count": result.rowcount,
        "retention_days": retention_days,
        "cutoff_date": cutoff_date.isoformat(),
    }

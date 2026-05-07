"""
Process Outbox Task
Polls outbox_events table and publishes to Redis Streams
Runs every minute for near-real-time event delivery
"""
from datetime import datetime
from typing import Optional
import structlog
import json

from celery import Task
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db_session
from ...core.db_ops import acquire_automation_lock
from ...models import OutboxEvent

logger = structlog.get_logger()

# Redis Streams configuration
REDIS_STREAM_KEY = "revenue_os:events"
MAX_EVENTS_PER_BATCH = 100


async def _publish_to_redis(redis_client, event: OutboxEvent) -> bool:
    """
    Publish event to Redis Streams.
    
    Args:
        redis_client: Redis client instance
        event: OutboxEvent to publish
    
    Returns:
        bool: True if published successfully
    """
    try:
        message = {
            "id": str(event.id),
            "aggregate_type": event.aggregate_type,
            "aggregate_id": event.aggregate_id,
            "event_type": event.event_type,
            "payload": json.dumps(event.payload),
            "headers": json.dumps(event.headers or {}),
            "correlation_id": event.correlation_id or "",
            "causation_id": event.causation_id or "",
            "created_at": event.created_at.isoformat() if event.created_at else "",
        }
        
        await redis_client.xadd(REDIS_STREAM_KEY, message)
        
        logger.debug(
            "outbox_event_published_to_redis",
            event_id=str(event.id),
            event_type=event.event_type,
            aggregate_type=event.aggregate_type,
        )
        
        return True
        
    except Exception as e:
        logger.error(
            "outbox_redis_publish_failed",
            event_id=str(event.id),
            error=str(e),
            error_type=type(e).__name__,
        )
        return False


async def _process_outbox_batch(
    db: AsyncSession,
    redis_client,
    batch_size: int = MAX_EVENTS_PER_BATCH,
) -> dict:
    """
    Process a batch of unprocessed outbox events.
    
    Args:
        db: Database session
        redis_client: Redis client
        batch_size: Maximum events to process
    
    Returns:
        dict: Processing metrics
    """
    from sqlalchemy import desc
    
    # Fetch unprocessed events
    result = await db.execute(
        select(OutboxEvent)
        .where(
            and_(
                OutboxEvent.processed == False,
                OutboxEvent.retry_count < 3,  # Max 3 retries
            )
        )
        .order_by(OutboxEvent.created_at)
        .limit(batch_size)
    )
    
    events = result.scalars().all()
    
    metrics = {
        "processed": 0,
        "failed": 0,
        "skipped": 0,
    }
    
    if not events:
        return metrics
    
    logger.info("outbox_processing_batch", count=len(events))
    
    for event in events:
        try:
            # Attempt to publish to Redis
            if await _publish_to_redis(redis_client, event):
                # Mark as processed
                event.processed = True
                event.processed_at = datetime.utcnow()
                metrics["processed"] += 1
            else:
                # Increment retry count
                event.retry_count += 1
                event.last_error = "Failed to publish to Redis"
                metrics["failed"] += 1
                
                if event.retry_count >= 3:
                    logger.error(
                        "outbox_event_max_retries_exceeded",
                        event_id=str(event.id),
                        event_type=event.event_type,
                    )
            
        except Exception as e:
            event.retry_count += 1
            event.last_error = str(e)[:500]  # Truncate long errors
            metrics["failed"] += 1
            
            logger.error(
                "outbox_event_processing_error",
                event_id=str(event.id),
                error=str(e),
                error_type=type(e).__name__,
            )
    
    await db.commit()
    
    logger.info(
        "outbox_batch_complete",
        **metrics,
        total=len(events),
    )
    
    return metrics


async def _process_outbox_impl(redis_client=None):
    """
    Process outbox implementation.
    
    Tasks:
    1. Acquire distributed lock
    2. Query unprocessed outbox events
    3. Publish to Redis Streams
    4. Mark events as processed
    5. Handle retries for failed events
    """
    async with get_db_session() as db:
        async with acquire_automation_lock(db, "process_outbox", ttl_seconds=120) as acquired:
            if not acquired:
                logger.debug("process_outbox: lock not acquired, skipping")
                return {
                    "status": "skipped",
                    "reason": "lock_held_by_another_worker",
                }
            
            try:
                # Get or create Redis client
                if redis_client is None:
                    redis_client = await _get_redis_client()
                
                if redis_client is None:
                    logger.error("process_outbox: no redis client available")
                    return {
                        "status": "error",
                        "reason": "redis_unavailable",
                    }
                
                # Process batch
                metrics = await _process_outbox_batch(db, redis_client)
                
                return {
                    "status": "completed",
                    "metrics": metrics,
                    "completed_at": datetime.utcnow().isoformat(),
                }
                
            except Exception as e:
                logger.error(
                    "process_outbox: failed",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                raise


async def _get_redis_client():
    """Get or create Redis client."""
    try:
        import os
        import aioredis
        
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        client = await aioredis.from_url(redis_url, decode_responses=True)
        return client
    except ImportError:
        logger.warning("aioredis not installed, outbox events will not be published to Redis")
        return None
    except Exception as e:
        logger.error("failed_to_create_redis_client", error=str(e))
        return None


def process_outbox(self: Task, redis_client=None):
    """
    Celery task wrapper for processing outbox events.
    
    Args:
        redis_client: Redis client (injected, optional)
    """
    import asyncio
    return asyncio.run(_process_outbox_impl(redis_client))

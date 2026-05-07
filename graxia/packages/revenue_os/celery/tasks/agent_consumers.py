"""
Agent Consumers Celery Task
Runs agent event handlers that consume from Redis Streams

Each agent type has its own consumer for isolation:
- VisionaryAgent: Strategic/campaign events
- SalesAgent: Lead/order events
- ChiefOfStaff: Approval/incident events
"""
from datetime import datetime
from typing import Dict, Any
import structlog
import asyncio

from celery import Task

from ...db import get_db_session
from ...core.db_ops import acquire_automation_lock
from ...core.redis_streams import RedisStreamClient, get_redis_client
from ...agents.event_handlers import (
    VisionaryAgentHandler,
    SalesAgentHandler,
    ChiefOfStaffHandler,
    route_event_to_handlers,
)

logger = structlog.get_logger()

# Consumer configuration
BLOCK_MS = 5000  # Block for 5 seconds waiting for events
BATCH_SIZE = 10  # Process max 10 events per iteration
MAX_ITERATIONS = 6  # 6 * 5s = 30s total runtime per task


async def _run_visionary_consumer(redis_client: RedisStreamClient) -> Dict[str, Any]:
    """Run Visionary Agent consumer."""
    metrics = {"processed": 0, "errors": 0}
    handler = VisionaryAgentHandler(redis_client)
    
    for _ in range(MAX_ITERATIONS):
        try:
            count = await redis_client.consume_events(
                consumer_name="visionary_agent",
                handler=handler.handle_event,
                block_ms=BLOCK_MS,
                count=BATCH_SIZE,
            )
            metrics["processed"] += count
            
            if count == 0:
                # No more events, break early
                break
                
        except Exception as e:
            metrics["errors"] += 1
            logger.error("visionary_consumer_error", error=str(e))
    
    return metrics


async def _run_sales_consumer(redis_client: RedisStreamClient) -> Dict[str, Any]:
    """Run Sales Agent consumer."""
    metrics = {"processed": 0, "errors": 0}
    handler = SalesAgentHandler(redis_client)
    
    for _ in range(MAX_ITERATIONS):
        try:
            count = await redis_client.consume_events(
                consumer_name="sales_agent",
                handler=handler.handle_event,
                block_ms=BLOCK_MS,
                count=BATCH_SIZE,
            )
            metrics["processed"] += count
            
            if count == 0:
                break
                
        except Exception as e:
            metrics["errors"] += 1
            logger.error("sales_consumer_error", error=str(e))
    
    return metrics


async def _run_chief_of_staff_consumer(redis_client: RedisStreamClient) -> Dict[str, Any]:
    """Run Chief of Staff Agent consumer."""
    metrics = {"processed": 0, "errors": 0}
    handler = ChiefOfStaffHandler(redis_client)
    
    for _ in range(MAX_ITERATIONS):
        try:
            count = await redis_client.consume_events(
                consumer_name="chief_of_staff_agent",
                handler=handler.handle_event,
                block_ms=BLOCK_MS,
                count=BATCH_SIZE,
            )
            metrics["processed"] += count
            
            if count == 0:
                break
                
        except Exception as e:
            metrics["errors"] += 1
            logger.error("chief_of_staff_consumer_error", error=str(e))
    
    return metrics


async def _claim_pending_messages(
    redis_client: RedisStreamClient,
    min_idle_ms: int = 60000,
) -> Dict[str, int]:
    """Claim and process pending messages from dead consumers."""
    results = {"claimed": 0, "processed": 0, "errors": 0}
    
    try:
        # Try to claim as each consumer type
        for consumer_name in ["visionary_agent", "sales_agent", "chief_of_staff_agent"]:
            claimed = await redis_client.claim_pending_messages(
                consumer_name=consumer_name,
                min_idle_ms=min_idle_ms,
                count=5,
            )
            
            results["claimed"] += len(claimed)
            
            # Process claimed messages
            for event in claimed:
                try:
                    route_results = await route_event_to_handlers(event)
                    if any(route_results.values()):
                        results["processed"] += 1
                    else:
                        results["errors"] += 1
                except Exception as e:
                    results["errors"] += 1
                    logger.error(
                        "claimed_message_processing_failed",
                        error=str(e),
                        event_type=event.get("event_type"),
                    )
    
    except Exception as e:
        logger.error("claim_pending_failed", error=str(e))
    
    return results


async def _agent_consumers_impl(redis_url: str = None) -> Dict[str, Any]:
    """
    Agent consumers implementation.
    
    Tasks:
    1. Acquire distributed lock
    2. Connect to Redis
    3. Run each agent consumer
    4. Claim and process pending messages
    5. Report metrics
    """
    async with get_db_session() as db:
        async with acquire_automation_lock(db, "agent_consumers", ttl_seconds=300) as acquired:
            if not acquired:
                logger.debug("agent_consumers: lock not acquired, skipping")
                return {
                    "status": "skipped",
                    "reason": "lock_held_by_another_worker",
                }
            
            try:
                # Connect to Redis
                redis_client = get_redis_client(redis_url)
                await redis_client.connect()
                
                # Ensure consumer group exists
                await redis_client.create_consumer_group()
                
                metrics = {
                    "visionary": {"processed": 0, "errors": 0},
                    "sales": {"processed": 0, "errors": 0},
                    "chief_of_staff": {"processed": 0, "errors": 0},
                    "pending_claimed": {"claimed": 0, "processed": 0, "errors": 0},
                }
                
                # Run all consumers concurrently
                visionary_task = _run_visionary_consumer(redis_client)
                sales_task = _run_sales_consumer(redis_client)
                cos_task = _run_chief_of_staff_consumer(redis_client)
                pending_task = _claim_pending_messages(redis_client)
                
                results = await asyncio.gather(
                    visionary_task,
                    sales_task,
                    cos_task,
                    pending_task,
                    return_exceptions=True,
                )
                
                # Process results
                if not isinstance(results[0], Exception):
                    metrics["visionary"] = results[0]
                else:
                    logger.error("visionary_consumer_failed", error=str(results[0]))
                    metrics["visionary"]["errors"] += 1
                
                if not isinstance(results[1], Exception):
                    metrics["sales"] = results[1]
                else:
                    logger.error("sales_consumer_failed", error=str(results[1]))
                    metrics["sales"]["errors"] += 1
                
                if not isinstance(results[2], Exception):
                    metrics["chief_of_staff"] = results[2]
                else:
                    logger.error("chief_of_staff_consumer_failed", error=str(results[2]))
                    metrics["chief_of_staff"]["errors"] += 1
                
                if not isinstance(results[3], Exception):
                    metrics["pending_claimed"] = results[3]
                
                # Disconnect
                await redis_client.disconnect()
                
                total_processed = (
                    metrics["visionary"]["processed"] +
                    metrics["sales"]["processed"] +
                    metrics["chief_of_staff"]["processed"] +
                    metrics["pending_claimed"]["processed"]
                )
                
                total_errors = (
                    metrics["visionary"]["errors"] +
                    metrics["sales"]["errors"] +
                    metrics["chief_of_staff"]["errors"] +
                    metrics["pending_claimed"]["errors"]
                )
                
                logger.info(
                    "agent_consumers_completed",
                    total_processed=total_processed,
                    total_errors=total_errors,
                    **metrics,
                )
                
                return {
                    "status": "completed",
                    "metrics": metrics,
                    "total_processed": total_processed,
                    "total_errors": total_errors,
                    "completed_at": datetime.utcnow().isoformat(),
                }
                
            except Exception as e:
                logger.error(
                    "agent_consumers: failed",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                raise


def agent_consumers(self: Task, redis_url: str = None):
    """
    Celery task wrapper for agent consumers.
    
    Runs every 30 seconds to consume Redis Stream events
    and route to appropriate agent handlers.
    
    Args:
        redis_url: Redis connection URL (optional)
    """
    import asyncio
    return asyncio.run(_agent_consumers_impl(redis_url))

"""
Hourly Monitor Task
Runs every hour to check system health
"""
from datetime import datetime, timedelta
import structlog

from celery import Task
from sqlalchemy import select, and_

from ...db import get_db_session
from ...core.db_ops import acquire_automation_lock, cleanup_expired_locks
from ...models import EmailOutbox, Order, Approval, AutomationLock
from ...enums import EmailStatus, OrderStatus, ApprovalStatus
from ...services.approval_service import ApprovalService

logger = structlog.get_logger()


async def _hourly_monitor_impl():
    """
    Hourly monitoring implementation.

    Tasks:
    1. Check for stale pending orders (> 30 min)
    2. Check EmailOutbox for stuck emails (retry_count > 3)
    3. Check for expired approvals
    4. Cleanup expired automation locks
    5. Emit health metrics
    """
    async with get_db_session() as db:
        async with acquire_automation_lock(db, "hourly_monitor", ttl_seconds=1800) as acquired:
            if not acquired:
                logger.warning("hourly_monitor: lock not acquired, skipping")
                return {
                    "status": "skipped",
                    "reason": "lock_held_by_another_worker",
                }

            try:
                metrics = {
                    "stale_orders": 0,
                    "stuck_emails": 0,
                    "expired_approvals": 0,
                    "expired_locks_cleaned": 0,
                }

                # 1. Check for stale pending orders
                logger.info("hourly_monitor: checking stale orders")
                thirty_min_ago = datetime.utcnow() - timedelta(minutes=30)

                result = await db.execute(
                    select(Order).where(
                        and_(
                            Order.status == OrderStatus.PENDING,
                            Order.created_at < thirty_min_ago,
                        )
                    )
                )
                stale_orders = result.scalars().all()
                metrics["stale_orders"] = len(stale_orders)

                if stale_orders:
                    logger.warning(
                        "hourly_monitor: stale orders detected",
                        count=len(stale_orders),
                        order_ids=[str(o.id) for o in stale_orders],
                    )

                # 2. Check EmailOutbox for stuck emails
                logger.info("hourly_monitor: checking stuck emails")
                result = await db.execute(
                    select(EmailOutbox).where(
                        and_(
                            EmailOutbox.status == EmailStatus.PENDING,
                            EmailOutbox.retry_count > 3,
                        )
                    )
                )
                stuck_emails = result.scalars().all()
                metrics["stuck_emails"] = len(stuck_emails)

                if stuck_emails:
                    logger.warning(
                        "hourly_monitor: stuck emails detected",
                        count=len(stuck_emails),
                        email_ids=[str(e.id) for e in stuck_emails],
                    )

                # 3. Check for expired approvals
                logger.info("hourly_monitor: checking expired approvals")
                expired_count = await ApprovalService.check_expired_approvals(
                    db, auto_reject=True
                )
                metrics["expired_approvals"] = expired_count

                # 4. Cleanup expired automation locks
                logger.info("hourly_monitor: cleaning expired locks")
                cleaned_locks = await cleanup_expired_locks(db)
                metrics["expired_locks_cleaned"] = cleaned_locks

                # 5. Emit health metrics
                logger.info(
                    "hourly_monitor: completed",
                    **metrics,
                )

                return {
                    "status": "completed",
                    "metrics": metrics,
                    "completed_at": datetime.utcnow().isoformat(),
                }

            except Exception as e:
                logger.error(
                    "hourly_monitor: failed",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                raise


def hourly_monitor(self: Task):
    """
    Celery task wrapper for hourly monitoring.
    """
    import asyncio
    return asyncio.run(_hourly_monitor_impl())

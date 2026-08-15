"""Digital fulfillment: sweep PAID orders missing delivery events (idempotent + locked)."""
from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db_session
from ...enums import OrderStatus
from ...models import DeliveryEvent, Order
from ...services.fulfillment_service import FulfillmentService
from ...core.db_ops import acquire_automation_lock

logger = structlog.get_logger()

LOCK_NAME = "digital_fulfillment"


async def sweep_pending_fulfillments(db: AsyncSession) -> int:
    """Fulfill every PAID order that has no delivery event yet. Returns count."""
    result = await db.execute(
        select(Order).where(Order.status == OrderStatus.PAID).order_by(Order.created_at)
    )
    orders = list(result.scalars().all())
    fulfilled = 0
    for order in orders:
        has_delivery = await db.scalar(
            select(DeliveryEvent.id).where(DeliveryEvent.order_id == order.id).limit(1)
        )
        if has_delivery:
            continue
        try:
            await FulfillmentService.fulfill_order(db, order.id, auto_queue_email=True)
            fulfilled += 1
        except Exception:
            logger.exception("digital_fulfillment_failed", order_id=str(order.id))
    await db.commit()
    return fulfilled


async def digital_fulfillment_with_db(db: AsyncSession) -> dict:
    """Lock-wrapped sweep. Skips when another worker holds the lock (Risk Audit #8).
    db-injected variant so tests can exercise the lock path without redis."""
    async with acquire_automation_lock(db, LOCK_NAME, ttl_seconds=300) as acquired:
        if not acquired:
            return {"skipped": True, "reason": "lock_held_by_another_worker"}
        fulfilled = await sweep_pending_fulfillments(db)
        return {"skipped": False, "fulfilled": fulfilled}


def digital_fulfillment():
    """Celery wrapper. Follows the asyncio.run pattern from agent_consumers.py."""
    import asyncio

    async def _impl():
        async with get_db_session() as db:
            return await digital_fulfillment_with_db(db)

    return asyncio.run(_impl())

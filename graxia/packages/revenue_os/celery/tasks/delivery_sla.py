"""Delivery SLA monitoring — PAID orders past SLA without delivery -> incident.

A PAID order older than SLA_DAYS with no DELIVERED DeliveryEvent raises an
open IncidentEvent MEDIUM once (per order) until resolved.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db_session
from ...core.db_ops import acquire_automation_lock
from ...enums import DeliveryStatus, IncidentSeverity, OrderStatus
from ...models import DeliveryEvent, IncidentEvent, Order

logger = structlog.get_logger()

LOCK_NAME = "delivery_sla"
SLA_DAYS = 7


async def delivery_sla_with_db(db: AsyncSession) -> dict:
    async with acquire_automation_lock(db, LOCK_NAME, ttl_seconds=600) as acquired:
        if not acquired:
            return {"skipped": True, "reason": "lock_held_by_another_worker"}
        cutoff = datetime.now(timezone.utc) - timedelta(days=SLA_DAYS)
        orders = (await db.execute(select(Order).where(
            Order.status == OrderStatus.PAID,
            Order.purchased_at < cutoff,
        ))).scalars().all()
        flagged = 0
        for order in orders:
            delivered = await db.scalar(select(DeliveryEvent.id).where(
                DeliveryEvent.order_id == order.id,
                DeliveryEvent.status == DeliveryStatus.DELIVERED,
            ))
            if delivered is not None:
                continue
            title = f"Delivery SLA breached: order {order.id}"
            open_incident = await db.scalar(select(IncidentEvent.id).where(
                IncidentEvent.title == title,
                IncidentEvent.status == "open",
            ))
            if open_incident is None:  # once per order until resolved
                db.add(IncidentEvent(
                    title=title,
                    description=(f"PAID since {order.purchased_at} — older than "
                                 f"{SLA_DAYS} days without a delivered event"),
                    severity=IncidentSeverity.MEDIUM, source="delivery_sla",
                    affected_order_id=order.id,
                ))
                flagged += 1
        await db.commit()
        return {"skipped": False, "checked": len(orders), "flagged": flagged}


def delivery_sla():
    import asyncio

    async def _impl():
        async with get_db_session() as db:
            return await delivery_sla_with_db(db)

    return asyncio.run(_impl())

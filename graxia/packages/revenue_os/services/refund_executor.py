"""Executes pending Refund rows against payment providers (Risk Audit #5).

Idempotent: a Refund that already has a platform_refund_id is never re-executed
(the (platform, platform_refund_id) unique constraint on Refund enforces this).
"""
from __future__ import annotations

import os

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import stripe
from datetime import datetime
from ..enums import RefundStatus
from ..models import Order, Refund

logger = structlog.get_logger()

stripe_refunds = stripe.Refund  # monkeypatch target for tests


class RefundExecutor:
    @staticmethod
    async def process_pending_refunds(db: AsyncSession) -> dict:
        result = await db.execute(
            select(Refund).where(Refund.status == RefundStatus.PROCESSING).order_by(Refund.created_at)
        )
        refunds = list(result.scalars().all())
        counts = {"processed": 0, "failed": 0, "skipped": 0}
        for refund in refunds:
            order = await db.get(Order, refund.order_id)
            if order is None or order.platform != "stripe":
                counts["skipped"] += 1
                continue
            if refund.platform_refund_id:
                counts["skipped"] += 1  # already processed
                continue
            try:
                stripe.api_key = os.getenv("STRIPE_API_KEY")
                created = stripe_refunds.create(
                    payment_intent=order.stripe_payment_intent,
                    amount=refund.amount_cents,
                    metadata={"refund_id": str(refund.id)},
                )
                refund.platform_refund_id = created.id
                refund.status = RefundStatus.PROCESSED
                refund.processed_at = datetime.utcnow()
                counts["processed"] += 1
            except Exception:
                logger.exception("refund_execution_failed", refund_id=str(refund.id))
                refund.status = RefundStatus.FAILED
                counts["failed"] += 1
        await db.commit()
        return counts

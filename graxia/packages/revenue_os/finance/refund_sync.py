"""Marketplace refund bookkeeping — HR-16: refunds must create ledger entries.

Marketplaces execute refunds on their own side; local automation books the
Refund row + negative REFUND ledger entry when reconcile observes a
RETURNED/REFUNDED status. Idempotent per order (one Refund row max).
RefundExecutor skips these (status=PROCESSED) — no Stripe call is made.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..enums import LedgerEntryType, RefundStatus
from ..models import LedgerEntry, Order, Refund


async def ensure_refund_record(db: AsyncSession, order: Order,
                               reason: str = "marketplace refund") -> bool:
    """Create a PROCESSED Refund + REFUND ledger entry once per order."""
    existing = await db.scalar(select(Refund).where(Refund.order_id == order.id))
    if existing is not None:
        return False  # idempotent
    db.add(Refund(
        order_id=order.id,
        platform=order.platform,
        platform_refund_id=f"{order.platform}-{order.platform_order_id}",
        amount_cents=order.amount_cents,
        currency=order.currency,
        reason=reason,
        status=RefundStatus.PROCESSED,  # marketplace handles the money move
    ))
    db.add(LedgerEntry(
        order_id=order.id,
        entry_type=LedgerEntryType.REFUND,
        amount_cents=-order.amount_cents,
        currency=order.currency,
        description=f"{order.platform} marketplace refund",
        metadata_={"platform": order.platform},
    ))
    await db.flush()
    return True

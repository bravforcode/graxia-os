"""Marketplace payout reconciliation — platform settlements -> ledger.

HR-04 (append-only ledger) + HR-10 (financial mutations through the ledger):
each settlement books a FEE entry (-fee) and a PAYOUT entry (+net received)
against the matching local order. Idempotent per settlement ref
(metadata_['settlement_ref']). Settlement data comes from a provider seam
(platform reports) wired at deployment.
"""
from __future__ import annotations

from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..enums import LedgerEntryType
from ..models import LedgerEntry, Order

logger = structlog.get_logger()


async def reconcile_payouts(db: AsyncSession, platform: str,
                            settlements: list[dict]) -> dict:
    """Book ledger entries for platform settlements.

    settlement shape: {order_id (platform order id), payout_cents (net),
    fee_cents (platform fee, optional), currency (optional), ref (settlement
    ref, optional but recommended — makes the row idempotent)}.
    """
    matched = created = skipped = 0
    for s in settlements:
        ref = s.get("ref")
        if ref:
            existing = await db.scalar(select(LedgerEntry).where(
                LedgerEntry.metadata_["settlement_ref"].astext == ref))
            if existing is not None:
                skipped += 1  # already booked for this settlement ref
                continue
        order = await db.scalar(select(Order).where(
            Order.platform == platform,
            Order.platform_order_id == str(s["order_id"]),
        ))
        if order is None:
            skipped += 1  # no local order -> cannot book
            continue
        currency = s.get("currency") or order.currency
        fee = int(s.get("fee_cents", 0))
        if fee:
            db.add(LedgerEntry(
                order_id=order.id, entry_type=LedgerEntryType.FEE,
                amount_cents=-fee, currency=currency,
                description=f"{platform} platform fee",
                metadata_={"settlement_ref": ref, "platform": platform},
            ))
        db.add(LedgerEntry(
            order_id=order.id, entry_type=LedgerEntryType.PAYOUT,
            amount_cents=int(s["payout_cents"]), currency=currency,
            description=f"{platform} payout",
            metadata_={"settlement_ref": ref, "platform": platform},
        ))
        matched += 1
        created += 1
    await db.commit()
    return {"matched": matched, "created": created, "skipped": skipped}


class PayoutProvider:
    """Provider seam for settlement data (platform reports/APIs).

    Deployment wires a subclass that implements fetch_settlements(platform);
    without one the task reports no_provider instead of failing.
    """

    async def fetch_settlements(self, platform: str) -> list[dict]:
        raise NotImplementedError


def provider_from_env() -> Optional[PayoutProvider]:
    """Build the configured provider, or None when not configured."""
    return None  # wired at deployment (runbook: payout-reconciliation)

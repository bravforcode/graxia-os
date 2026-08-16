"""Affiliate/KOL program — policy-gated commissions, attribution tracking,
payout review (manual processing for Phase 3).

- create_affiliate: rejects commission above the AFFILIATE PERCENT cap
- record_attribution: ACTIVE affiliate + order within ATTRIBUTION_WINDOW_DAYS
  of first touch (AttributionEvent reuse); creates pending AffiliatePayout;
  >= AFFILIATE_REVIEW_THRESHOLD_CENTS -> needs_review + IncidentEvent MEDIUM
- review_payouts: daily sweep flags threshold rows + Telegram summary;
  payouts stay manual (pending -> approved only after human review)
"""
from __future__ import annotations

from typing import Optional
from uuid import uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import AFFILIATE_REVIEW_THRESHOLD_CENTS, ATTRIBUTION_WINDOW_DAYS
from ..core.policy_engine import PolicyEngine
from ..enums import ActionType, AffiliateStatus, IncidentSeverity
from ..models import Affiliate, AffiliatePayout, AttributionEvent, IncidentEvent, Order

logger = structlog.get_logger()


class AffiliateError(Exception):
    """Raised when an affiliate operation is rejected (policy, validation)."""


def _code_from_email(email: str) -> str:
    local = (email.split("@")[0] or "aff").lower()
    return f"{local[:20]}{uuid4().hex[:6]}"


async def create_affiliate(db: AsyncSession, email: str, commission_percent: float,
                           code: Optional[str] = None) -> Affiliate:
    """Create an affiliate; commission above the AFFILIATE PERCENT cap is rejected
    by the policy engine (fail-closed when no rules are seeded)."""
    decision = await PolicyEngine.check(
        db, ActionType.AFFILIATE,
        {"value": commission_percent, "value_cents": 0, "currency": "THB"},
    )
    if not decision.allow:
        raise AffiliateError(
            f"commission {commission_percent}% rejected by policy: {decision.reason}")
    affiliate = Affiliate(code=code or _code_from_email(email), email=email,
                          commission_percent=commission_percent,
                          status=AffiliateStatus.ACTIVE)
    db.add(affiliate)
    await db.commit()
    return affiliate


async def record_attribution(db: AsyncSession, affiliate_code: str, order_id) -> bool:
    """Attribute a confirmed order to an affiliate.

    Requires: affiliate exists + ACTIVE, order exists, a first-touch
    AttributionEvent exists (source=code, order_id=order), and the order is
    within ATTRIBUTION_WINDOW_DAYS of that touch. No double payouts.
    """
    affiliate = await db.scalar(select(Affiliate).where(Affiliate.code == affiliate_code))
    if affiliate is None or affiliate.status != AffiliateStatus.ACTIVE:
        return False
    order = await db.get(Order, order_id)
    if order is None:
        return False
    existing = await db.scalar(select(AffiliatePayout).where(
        AffiliatePayout.affiliate_id == affiliate.id,
        AffiliatePayout.order_id == order.id,
    ))
    if existing is not None:
        return False  # idempotent: no double payouts
    touch = await db.scalar(select(AttributionEvent).where(
        AttributionEvent.source == affiliate_code,
        AttributionEvent.order_id == order.id,
    ).order_by(AttributionEvent.created_at.asc()).limit(1))
    if touch is None:
        return False  # no recorded touch -> nothing to attribute
    purchased = order.purchased_at or order.created_at
    if touch.created_at is not None and purchased is not None:
        try:
            days = (purchased - touch.created_at).total_seconds() / 86400.0
        except TypeError:
            days = ATTRIBUTION_WINDOW_DAYS + 1  # tz mismatch -> fail closed
        if days > ATTRIBUTION_WINDOW_DAYS:
            return False  # outside the 30-day attribution window
    amount_cents = int(order.amount_cents * (affiliate.commission_percent / 100.0))
    payout = AffiliatePayout(affiliate_id=affiliate.id, order_id=order.id,
                             amount_cents=amount_cents, status="pending")
    if amount_cents >= AFFILIATE_REVIEW_THRESHOLD_CENTS:
        payout.needs_review = True
        db.add(IncidentEvent(
            title=f"Affiliate payout needs review: {affiliate.code}",
            description=(f"{amount_cents} cents >= review threshold "
                         f"{AFFILIATE_REVIEW_THRESHOLD_CENTS}"),
            severity=IncidentSeverity.MEDIUM, source="affiliate",
            affected_order_id=order.id,
        ))
    db.add(payout)
    await db.commit()
    return True


async def review_payouts(db: AsyncSession, notifier=None) -> dict:
    """Daily sweep: flag every pending row at/above the review threshold that
    is not yet flagged. Payouts remain manual for Phase 3 (operator approves
    pending -> approved); a Telegram summary is sent when rows are flagged."""
    rows = (await db.execute(select(AffiliatePayout).where(
        AffiliatePayout.status == "pending",
        AffiliatePayout.needs_review.is_(False),
        AffiliatePayout.amount_cents >= AFFILIATE_REVIEW_THRESHOLD_CENTS,
    ))).scalars().all()
    for payout in rows:
        payout.needs_review = True
    await db.commit()
    flagged = len(rows)
    if flagged and notifier is not None:
        summary = (f"Affiliate review: {flagged} payout(s) flagged for review "
                   f"(threshold {AFFILIATE_REVIEW_THRESHOLD_CENTS} cents)")
        try:
            await notifier().send_message(text=summary)
        except Exception:
            logger.exception("affiliate_review_telegram_failed")
    return {"flagged": flagged}

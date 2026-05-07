"""
Usage limit enforcement middleware.
Check BEFORE action. Log AFTER success.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.models.organization import Organization
from app.models.usage_log import UsageLog
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def check_and_log(
    db: AsyncSession,
    org: Organization,
    feature: str,
    quantity: int = 1,
    cost_usd: Decimal | None = None,
    user_id: uuid.UUID | None = None,
    meta: dict | None = None,
) -> None:
    """
    Raises HTTP 402/403 if org is over limit.
    Logs usage on success.
    Always awaits — never blocks.
    """
    # Paid plan: never block
    if org.plan == "pro":
        await _write_log(db, org.id, user_id, feature, quantity, cost_usd, meta)
        return

    # Block non-active orgs
    if org.status == "canceled":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Subscription canceled. Renew at /settings/billing.",
        )
    if org.status == "past_due":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Payment overdue. Update your payment method.",
        )
    if org.status == "suspended":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account suspended. Contact support.",
        )

    # Check lead limit (free + starter)
    if feature == "lead_discovery":
        used = await _month_usage(db, org.id, feature)
        if used + quantity > org.monthly_lead_limit:
            remaining = max(0, org.monthly_lead_limit - used)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Monthly lead limit: {org.monthly_lead_limit}. "
                    f"Used {used}, {remaining} remaining. "
                    f"Upgrade to Pro for unlimited leads."
                ),
            )

    await _write_log(db, org.id, user_id, feature, quantity, cost_usd, meta)


async def _month_usage(db: AsyncSession, org_id: uuid.UUID, feature: str) -> int:
    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.coalesce(func.sum(UsageLog.quantity), 0))
        .where(UsageLog.organization_id == org_id)
        .where(UsageLog.feature == feature)
        .where(UsageLog.created_at >= month_start)
    )
    return int(result.scalar() or 0)


async def _write_log(
    db: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
    feature: str,
    quantity: int,
    cost_usd: Decimal | None,
    meta: dict | None,
) -> None:
    db.add(
        UsageLog(
            organization_id=org_id,
            user_id=user_id,
            feature=feature,
            quantity=quantity,
            cost_usd=cost_usd,
            meta=meta or {},
        )
    )
    # Caller is responsible for committing

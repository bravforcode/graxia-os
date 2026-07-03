"""
Billing endpoints. Stripe checkout, portal, usage, cancellation.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.stripe_client import (
    cancel_stripe_subscription,
    create_stripe_customer,
    create_stripe_subscription,
    get_portal_url,
    get_price_id,
)
from app.database import get_db
from app.middleware.auth import get_current_user_from_token
from app.models.organization import PLAN_LIMITS, Organization
from app.models.usage_log import UsageLog
from app.models.user import User

router = APIRouter(prefix="/billing", tags=["billing"])


class CheckoutIn(BaseModel):
    plan: str  # "starter" | "pro"


@router.get("/plans")
async def list_plans():
    """List available subscription plans."""
    return {
        "plans": [
            {"id": "free", "name": "Free", "limits": PLAN_LIMITS["free"]},
            {"id": "starter", "name": "Starter", "limits": PLAN_LIMITS["starter"]},
            {"id": "pro", "name": "Pro", "limits": PLAN_LIMITS["pro"]},
        ]
    }


@router.post("/checkout")
async def start_checkout(
    body: CheckoutIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_from_token),
):
    """Start 14-day free trial. No card required during trial."""
    if body.plan not in PLAN_LIMITS or body.plan == "free":
        raise HTTPException(status_code=400, detail=f"Invalid plan: {body.plan}")

    price_id = await get_price_id(body.plan)
    if not price_id:
        raise HTTPException(
            status_code=503,
            detail="Billing not configured. Contact support@graxia.io",
        )

    org: Organization | None = user.organization
    if not org:
        raise HTTPException(status_code=400, detail="No organization found")

    if org.stripe_subscription_id:
        raise HTTPException(
            status_code=400, detail="Already subscribed. Use /billing/portal to change plan."
        )

    # Create Stripe customer
    if not org.stripe_customer_id:
        customer = await create_stripe_customer(
            email=user.email,
            name=user.full_name or user.email,
            org_id=str(org.id),
        )
        org.stripe_customer_id = customer.id
        await db.flush()

    sub = await create_stripe_subscription(
        customer_id=org.stripe_customer_id,
        price_id=price_id,
        trial_days=14,
    )

    org.stripe_subscription_id = sub.id
    org.plan = body.plan
    org.status = "trialing"
    org.trial_ends_at = datetime.now(UTC) + timedelta(days=14)
    org.apply_plan_limits()

    await db.commit()

    client_secret = None
    try:
        if sub.latest_invoice and sub.latest_invoice.payment_intent:
            client_secret = sub.latest_invoice.payment_intent.client_secret
    except Exception:
        pass

    return {
        "subscription_id": sub.id,
        "status": sub.status,
        "trial_end": org.trial_ends_at.isoformat(),
        "client_secret": client_secret,
    }


@router.post("/portal")
async def open_portal(
    request: Request,
    user: User = Depends(get_current_user_from_token),
):
    """Open Stripe Customer Portal for self-service management."""
    org = user.organization
    if not org or not org.stripe_customer_id:
        raise HTTPException(
            status_code=400,
            detail="No subscription. Start one at /billing/checkout",
        )
    return_url = f"{settings.FRONTEND_URL}/settings/billing"
    url = await get_portal_url(org.stripe_customer_id, return_url)
    return {"url": url}


@router.get("/usage")
async def get_usage(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_from_token),
):
    """Current month usage vs plan limits."""
    org = user.organization
    if not org:
        raise HTTPException(status_code=400, detail="No organization")

    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = await db.execute(
        select(UsageLog.feature, func.sum(UsageLog.quantity).label("total"))
        .where(UsageLog.organization_id == org.id)
        .where(UsageLog.created_at >= month_start)
        .group_by(UsageLog.feature)
    )
    usage = {r.feature: int(r.total) for r in rows}

    return {
        "plan": org.plan,
        "status": org.status,
        "trial_ends_at": org.trial_ends_at.isoformat() if org.trial_ends_at else None,
        "limits": {
            "leads_per_month": org.monthly_lead_limit,
            "ai_credits_cents": org.monthly_ai_credit_cents,
            "seats": org.seats,
        },
        "usage": {
            "leads": usage.get("lead_discovery", 0),
            "drafts": usage.get("draft_generation", 0),
            "emails": usage.get("email_send", 0),
        },
        "upgrade_url": f"{settings.FRONTEND_URL}/billing",
    }


@router.post("/cancel")
async def cancel_plan(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_from_token),
):
    """Cancel at end of billing period. Does not immediately downgrade."""
    org = user.organization
    if not org or not org.stripe_subscription_id:
        raise HTTPException(status_code=400, detail="No active subscription")
    await cancel_stripe_subscription(org.stripe_subscription_id)
    # Webhook will handle actual downgrade when period ends
    return {"message": "Subscription will cancel at end of billing period."}

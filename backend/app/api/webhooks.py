"""
Stripe webhook handler.
Idempotent — safe to receive duplicate events.
This is the ONLY place subscription state changes happen.
"""

import logging

import sqlalchemy as sa
import stripe
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = logging.getLogger("graxia.webhooks")


async def _org_by_customer(db: AsyncSession, cid: str) -> Organization | None:
    r = await db.execute(select(Organization).where(Organization.stripe_customer_id == cid))
    return r.scalar_one_or_none()


@router.post("/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    if not settings.STRIPE_WEBHOOK_SECRET:
        log.error("STRIPE_WEBHOOK_SECRET not configured")
        raise HTTPException(status_code=500, detail="Webhook not configured")

    try:
        event = stripe.Webhook.construct_event(payload, sig, settings.STRIPE_WEBHOOK_SECRET)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Idempotency check
    event_id = event.get("id")
    if event_id and getattr(request.app.state, "redis", None):
        redis = request.app.state.redis
        is_new = await redis.set(f"stripe_event:{event_id}", "1", nx=True, ex=86400)
        if not is_new:
            log.info(f"Duplicate Stripe event skipped: {event_id}")
            return {"received": True, "duplicate": True}

    async for db in get_db():
        await _dispatch(event, db)
        break

    return {"received": True}


async def _dispatch(event: dict, db: AsyncSession) -> None:
    etype = event["type"]
    data = event["data"]["object"]
    cid = data.get("customer")
    log.info(f"Stripe event: {etype} customer={cid}")

    if not cid:
        return

    if etype == "invoice.payment_succeeded":
        org = await _org_by_customer(db, cid)
        if org:
            org.status = "active"
            # Refresh plan limits from subscription
            sub_id = data.get("subscription")
            if sub_id:
                try:
                    sub = stripe.Subscription.retrieve(sub_id)
                    pid = sub["items"]["data"][0]["price"]["id"]
                    from app.core.stripe_client import get_price_id

                    plan = next(
                        (k for k in ["starter", "pro"] if await get_price_id(k) == pid),
                        org.plan,
                    )
                    org.plan = plan
                    org.apply_plan_limits()
                except Exception as e:
                    log.error(f"Plan refresh error: {e}")
            await db.commit()
            log.info(f"Org {org.id} → active (plan={org.plan})")

    elif etype == "invoice.payment_failed":
        org = await _org_by_customer(db, cid)
        if org:
            org.status = "past_due"
            await db.commit()
            log.warning(f"Org {org.id} → past_due")
            # Send payment failed email to org owner
            try:
                from app.services.email_service import send_payment_failed_email
                # Get first user in org as owner
                owner = await db.execute(
                    sa.select(User).where(User.organization_id == org.id).limit(1)
                )
                owner = owner.scalar_one_or_none()
                if owner:
                    await send_payment_failed_email(
                        to=owner.email,
                        to_name=owner.full_name or owner.email.split("@")[0],
                    )
            except Exception as e:
                log.error(f"Failed to send payment failed email: {e}")

    elif etype == "customer.subscription.deleted":
        org = await _org_by_customer(db, cid)
        if org:
            org.status = "canceled"
            org.plan = "free"
            org.stripe_subscription_id = None
            org.apply_plan_limits()
            await db.commit()
            log.info(f"Org {org.id} → canceled, downgraded to free")

    elif etype == "customer.subscription.trial_will_end":
        org = await _org_by_customer(db, cid)
        if org:
            log.info(f"Trial ending for org {org.id}")
            # Send trial ending email
            try:
                from app.services.email_service import send_trial_ending_email
                owner = await db.execute(
                    sa.select(User).where(User.organization_id == org.id).limit(1)
                )
                owner = owner.scalar_one_or_none()
                if owner and org.trial_ends_at:
                    from datetime import UTC, datetime
                    days_left = max(1, (org.trial_ends_at - datetime.now(UTC)).days)
                    await send_trial_ending_email(
                        to=owner.email,
                        to_name=owner.full_name or owner.email.split("@")[0],
                        days_left=days_left,
                    )
            except Exception as e:
                log.error(f"Failed to send trial ending email: {e}")

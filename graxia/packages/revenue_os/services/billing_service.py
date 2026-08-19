"""SaaS subscription billing (P2-10).

Stripe is the source of truth for billing; the Subscription row mirrors the
lifecycle so entitlements/reporting can read locally. All Stripe calls go
through module-level monkeypatch targets (refund_executor pattern).
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional
from uuid import UUID

import stripe
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Customer, Subscription

logger = structlog.get_logger()

stripe_subscriptions = stripe.Subscription  # monkeypatch target for tests
stripe_billing_portal = stripe.billing_portal.Session  # monkeypatch target for tests

# THB cents — matches seed pricing (docs/investor/01-pitch-deck.md)
PLAN_PRICES_CENTS: dict[str, int] = {
    "standard": 490_000,    # 4,900 THB/mo
    "enterprise": 1_990_000,  # 19,900 THB/mo
}


def _get_stripe_secret_key() -> str:
    key = os.getenv("STRIPE_SECRET_KEY") or os.getenv("STRIPE_API_KEY")
    if not key:
        if os.getenv("APP_ENV") == "production":
            raise RuntimeError("STRIPE_SECRET_KEY must be set in production")
        return "sk_test_placeholder"
    return key


class BillingService:
    @staticmethod
    async def create_subscription(
        db: AsyncSession,
        customer_email: str,
        plan: str,
        trial_days: int = 14,
    ) -> Subscription:
        """Create a Stripe subscription + local mirror row. Idempotent per customer."""
        if plan not in PLAN_PRICES_CENTS:
            raise ValueError(f"unknown plan '{plan}' (valid: {list(PLAN_PRICES_CENTS)})")

        # Idempotency: one active subscription per customer
        existing = await db.scalar(
            select(Subscription).where(
                Subscription.customer_email == customer_email,
                Subscription.status == "active",
            )
        )
        if existing:
            return existing

        customer = await db.scalar(
            select(Customer).where(Customer.email == customer_email)
        )

        stripe.api_key = _get_stripe_secret_key()
        created = stripe_subscriptions.create(
            customer=customer.stripe_customer_id if customer else None,
            items=[{"price_data": {
                "currency": "thb",
                "unit_amount": PLAN_PRICES_CENTS[plan],
                "product_data": {"name": f"Graxia Revenue OS — {plan.title()}"},
                "recurring": {"interval": "month"},
            }}],
            trial_period_days=trial_days,
            payment_behavior="default_incomplete",
            metadata={"plan": plan, "customer_email": customer_email},
        )

        sub = Subscription(
            customer_id=customer.id if customer else None,
            customer_email=customer_email,
            plan=plan,
            status="active",
            stripe_subscription_id=created.id,
            price_cents=PLAN_PRICES_CENTS[plan],
            currency="THB",
            current_period_end=datetime.utcnow(),
        )
        db.add(sub)
        await db.commit()
        logger.info("subscription_created", plan=plan, customer_email=customer_email)
        return sub

    @staticmethod
    async def cancel_subscription(db: AsyncSession, subscription_id: UUID) -> Subscription:
        sub = await db.get(Subscription, subscription_id)
        if sub is None:
            raise ValueError(f"Subscription {subscription_id} not found")
        if sub.status != "active":
            return sub

        stripe.api_key = _get_stripe_secret_key()
        stripe_subscriptions.cancel(sub.stripe_subscription_id)

        sub.status = "canceled"
        sub.canceled_at = datetime.utcnow()
        await db.commit()
        logger.info("subscription_canceled", subscription_id=str(subscription_id))
        return sub

    @staticmethod
    async def handle_subscription_deleted(db: AsyncSession, stripe_sub: dict) -> Optional[Subscription]:
        """Webhook: customer.subscription.deleted → mark local row canceled."""
        sid = stripe_sub.get("id")
        if not sid:
            return None
        sub = await db.scalar(
            select(Subscription).where(Subscription.stripe_subscription_id == sid)
        )
        if sub is None:
            return None
        sub.status = "canceled"
        sub.canceled_at = datetime.utcnow()
        await db.commit()
        logger.info("subscription_deleted_webhook", stripe_subscription_id=sid)
        return sub

    @staticmethod
    async def handle_subscription_created(db: AsyncSession, stripe_sub: dict) -> Optional[Subscription]:
        """Webhook: customer.subscription.created → mirror row (idempotent)."""
        sid = stripe_sub.get("id")
        if not sid:
            return None
        existing = await db.scalar(
            select(Subscription).where(Subscription.stripe_subscription_id == sid)
        )
        if existing:
            return existing
        metadata = stripe_sub.get("metadata", {}) or {}
        items = stripe_sub.get("items", {}).get("data", []) or []
        price_cents = 0
        if items:
            price_cents = items[0].get("price", {}).get("unit_amount") or 0
        sub = Subscription(
            customer_email=metadata.get("customer_email") or "",
            plan=metadata.get("plan") or "starter",
            status="active",
            stripe_subscription_id=sid,
            price_cents=price_cents,
            currency="THB",
            current_period_end=datetime.utcnow(),
        )
        db.add(sub)
        await db.commit()
        logger.info("subscription_created_webhook", stripe_subscription_id=sid)
        return sub

    @staticmethod
    async def create_portal_session(db: AsyncSession, customer_email: str) -> str:
        """Create a Stripe billing portal session URL for a customer."""
        customer = await db.scalar(
            select(Customer).where(Customer.email == customer_email)
        )
        if customer is None or not customer.stripe_customer_id:
            raise ValueError(f"no Stripe customer for {customer_email}")
        stripe.api_key = _get_stripe_secret_key()
        session = stripe_billing_portal.create(customer=customer.stripe_customer_id)
        return session.url
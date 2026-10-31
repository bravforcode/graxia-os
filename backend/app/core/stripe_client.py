"""
Stripe wrapper. All Stripe calls go through here.
Never import stripe directly in API routes.
"""

import asyncio

import stripe

from app.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY

PLAN_PRICE_MAP: dict[str, str] = {}  # populated at runtime


def _ensure_stripe_write_allowed(operation: str) -> None:
    secret_key = str(getattr(settings, "STRIPE_SECRET_KEY", "") or "").strip()
    if any(
        secret_key.startswith(prefix) and len(secret_key) > len(prefix)
        for prefix in ("sk_test_", "rk_test_")
    ):
        return
    if secret_key.startswith(("sk_live_", "rk_live_")):
        if getattr(settings, "ALLOW_LIVE_STRIPE", False) is True:
            return
        raise RuntimeError(f"Live Stripe {operation} is disabled")
    raise RuntimeError(
        "Stripe writes are disabled without a recognized test key or live consent"
    )


def _price_map() -> dict[str, str]:
    return {
        "starter": settings.STRIPE_PRICE_STARTER_MONTHLY,
        "pro": settings.STRIPE_PRICE_PRO_MONTHLY,
        "enterprise": settings.STRIPE_PRICE_ENTERPRISE_MONTHLY,
    }


async def create_stripe_customer(email: str, name: str, org_id: str) -> stripe.Customer:
    _ensure_stripe_write_allowed("customer creation")
    return await asyncio.to_thread(
        stripe.Customer.create,
        email=email,
        name=name,
        metadata={"organization_id": org_id, "source": "graxia"},
    )


async def create_stripe_subscription(
    customer_id: str,
    price_id: str,
    trial_days: int = 14,
) -> stripe.Subscription:
    _ensure_stripe_write_allowed("subscription creation")
    return await asyncio.to_thread(
        stripe.Subscription.create,
        customer=customer_id,
        items=[{"price": price_id}],
        trial_period_days=trial_days,
        payment_behavior="default_incomplete",
        expand=["latest_invoice.payment_intent"],
    )


async def cancel_stripe_subscription(subscription_id: str) -> stripe.Subscription:
    _ensure_stripe_write_allowed("subscription cancellation")
    return await asyncio.to_thread(stripe.Subscription.cancel, subscription_id)


async def create_stripe_checkout_session(
    customer_id: str | None,
    success_url: str,
    cancel_url: str,
    line_items: list[dict],
    metadata: dict,
    customer_email: str | None = None,
) -> stripe.checkout.Session:
    _ensure_stripe_write_allowed("Checkout")

    params = {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "line_items": line_items,
        "metadata": metadata,
    }
    # PromptPay (TH) — enabled only when the merchant has activated it in the
    # Stripe dashboard (STRIPE_ENABLE_PROMPTPAY=1). Off by default so checkout
    # never breaks on accounts without the payment method enabled.
    if settings.STRIPE_ENABLE_PROMPTPAY and line_items and line_items[0].get("price_data", {}).get("currency") == "thb":
        params["payment_method_types"] = ["card", "promptpay"]
    if customer_id:
        params["customer"] = customer_id
    elif customer_email:
        params["customer_email"] = customer_email
    
    return await asyncio.to_thread(stripe.checkout.Session.create, **params)


async def get_portal_url(customer_id: str, return_url: str) -> str:
    _ensure_stripe_write_allowed("billing portal session creation")
    session = await asyncio.to_thread(
        stripe.billing_portal.Session.create,
        customer=customer_id,
        return_url=return_url,
    )
    return session.url


async def get_price_id(plan: str) -> str | None:
    return _price_map().get(plan)

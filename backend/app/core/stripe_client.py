"""
Stripe wrapper. All Stripe calls go through here.
Never import stripe directly in API routes.
"""

import stripe

from app.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY

PLAN_PRICE_MAP: dict[str, str] = {}  # populated at runtime


def _price_map() -> dict[str, str]:
    return {
        "starter": settings.STRIPE_PRICE_STARTER,
        "pro": settings.STRIPE_PRICE_PRO,
    }


async def create_stripe_customer(email: str, name: str, org_id: str) -> stripe.Customer:
    return stripe.Customer.create(
        email=email,
        name=name,
        metadata={"organization_id": org_id, "source": "graxia"},
    )


async def create_stripe_subscription(
    customer_id: str,
    price_id: str,
    trial_days: int = 14,
) -> stripe.Subscription:
    return stripe.Subscription.create(
        customer=customer_id,
        items=[{"price": price_id}],
        trial_period_days=trial_days,
        payment_behavior="default_incomplete",
        expand=["latest_invoice.payment_intent"],
    )


async def cancel_stripe_subscription(subscription_id: str) -> stripe.Subscription:
    return stripe.Subscription.cancel(subscription_id)


async def create_stripe_checkout_session(
    customer_id: str | None,
    success_url: str,
    cancel_url: str,
    line_items: list[dict],
    metadata: dict,
    customer_email: str | None = None,
) -> stripe.checkout.Session:
    params = {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "line_items": line_items,
        "metadata": metadata,
    }
    if customer_id:
        params["customer"] = customer_id
    elif customer_email:
        params["customer_email"] = customer_email
    
    return stripe.checkout.Session.create(**params)


async def get_portal_url(customer_id: str, return_url: str) -> str:
    session = stripe.billing_portal.Session.create(customer=customer_id, return_url=return_url)
    return session.url


async def get_price_id(plan: str) -> str | None:
    return _price_map().get(plan)

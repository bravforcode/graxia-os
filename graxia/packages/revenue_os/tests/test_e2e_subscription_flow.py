"""P0 E2E: subscription checkout → webhook → mirror row → portal → kill switch."""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from graxia.services.revenue_os_api.routers.checkout import (
    create_checkout_session,
    stripe_checkout,
    stripe_webhook,
)
from ..enums import ProductStatus, ProductType
from ..models import Product, Subscription
from ..schemas import CheckoutSessionCreate
from ..services.billing_service import BillingService, stripe_billing_portal


class _FakeSession:
    def __init__(self, session_id="cs_test_e2e", url="https://checkout.stripe.com/c/pay/cs_test_e2e"):
        self.id = session_id
        self.url = url


class _FakePortalSession:
    url = "https://billing.stripe.com/session/e2e"


@pytest.mark.asyncio
async def test_full_subscription_flow(db_session: AsyncSession, monkeypatch):
    # 1. Product (Starter tier)
    product = Product(
        name="Revenue OS Starter",
        slug="revenue-os-starter-e2e",
        type=ProductType.CORE,
        price_cents=49900,
        currency="THB",
        status=ProductStatus.PUBLISHED,
    )
    db_session.add(product)
    await db_session.flush()

    # 2. Checkout session (subscription mode)
    captured = {}
    monkeypatch.setattr(stripe_checkout, "create", lambda **kwargs: (captured.update(kwargs) or _FakeSession()))
    payload = CheckoutSessionCreate(
        product_id=product.id,
        customer_email="buyer@example.com",
        success_url="https://example.com/success",
        cancel_url="https://example.com/cancel",
        mode="subscription",
    )
    resp = await create_checkout_session(payload, db_session)
    assert resp.session_id == "cs_test_e2e"
    assert captured["mode"] == "subscription"

    # 3. Webhook: checkout.session.completed → order PAID (existing path)
    checkout_event = {
        "id": "evt_checkout_e2e",
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_test_e2e",
            "customer_email": "buyer@example.com",
            "metadata": {"product_id": str(product.id), "mode": "subscription"},
            "payment_intent": "pi_test_e2e",
            "amount_total": 49900,
            "currency": "thb",
        }},
    }
    # 4. Webhook: customer.subscription.created → mirror row
    sub_event = {
        "id": "evt_sub_e2e",
        "type": "customer.subscription.created",
        "data": {"object": {
            "id": "sub_test_e2e",
            "metadata": {"plan": "starter", "customer_email": "buyer@example.com"},
            "items": {"data": [{"price": {"unit_amount": 49900}}]},
        }},
    }
    # Call handlers directly (HMAC is covered by require_stripe_hmac tests)
    from ..services.webhook_processor import WebhookProcessor
    order = await WebhookProcessor.process_stripe_checkout_completed(checkout_event["data"]["object"], db_session)
    assert order is not None
    sub = await BillingService.handle_subscription_created(db_session, sub_event["data"]["object"])
    assert sub is not None and sub.status == "active"

    # 5. Billing portal session
    from ..models import Customer
    # Webhook fulfillment already created the customer — attach Stripe customer id
    customer = await db_session.scalar(
        select(Customer).where(Customer.email == "buyer@example.com")
    )
    assert customer is not None  # created by process_stripe_checkout_completed
    customer.stripe_customer_id = "cus_test_e2e"
    await db_session.flush()
    monkeypatch.setattr(stripe_billing_portal, "create", lambda **kwargs: _FakePortalSession())
    url = await BillingService.create_portal_session(db_session, "buyer@example.com")
    assert url == "https://billing.stripe.com/session/e2e"

    # 6. Kill switch blocks new checkout
    from fastapi import HTTPException
    from ..services.kill_switch import MoneyKillSwitch
    import tempfile, os
    ks_path = os.path.join(tempfile.mkdtemp(), "ks.json")
    monkeypatch.setenv("REVENUE_OS_KILL_SWITCH_FILE", ks_path)
    MoneyKillSwitch(ks_path).trigger("e2e test")
    with pytest.raises(HTTPException) as exc:
        await create_checkout_session(payload, db_session)
    assert exc.value.status_code == 503
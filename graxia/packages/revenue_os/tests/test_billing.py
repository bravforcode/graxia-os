"""Tests for SaaS subscription billing (P2-10)."""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Subscription
from ..services.billing_service import BillingService, stripe_subscriptions


class _FakeSubscription:
    def __init__(self, sid="sub_test_123"):
        self.id = sid


@pytest.mark.asyncio
async def test_create_subscription_success(db_session: AsyncSession, monkeypatch):
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return _FakeSubscription()

    monkeypatch.setattr(stripe_subscriptions, "create", fake_create)

    sub = await BillingService.create_subscription(
        db_session, "buyer@example.com", "standard"
    )
    assert sub.plan == "standard"
    assert sub.status == "active"
    assert sub.price_cents == 490_000
    assert sub.stripe_subscription_id == "sub_test_123"
    # Stripe call carries THB price + plan metadata
    assert captured["items"][0]["price_data"]["unit_amount"] == 490_000
    assert captured["metadata"]["plan"] == "standard"


@pytest.mark.asyncio
async def test_create_subscription_idempotent(db_session: AsyncSession, monkeypatch):
    calls = []

    def fake_create(**kwargs):
        calls.append(kwargs)
        return _FakeSubscription(f"sub_{len(calls)}")

    monkeypatch.setattr(stripe_subscriptions, "create", fake_create)

    await BillingService.create_subscription(db_session, "buyer@example.com", "standard")
    again = await BillingService.create_subscription(db_session, "buyer@example.com", "standard")
    assert len(calls) == 1  # second call reuses active row, no Stripe call
    assert again.status == "active"


@pytest.mark.asyncio
async def test_create_subscription_unknown_plan(db_session: AsyncSession):
    with pytest.raises(ValueError):
        await BillingService.create_subscription(db_session, "buyer@example.com", "gold")


@pytest.mark.asyncio
async def test_cancel_subscription(db_session: AsyncSession, monkeypatch):
    cancelled = []

    def fake_create(**kwargs):
        return _FakeSubscription("sub_test_123")

    def fake_cancel(sid):
        cancelled.append(sid)
        return _FakeSubscription(sid)

    monkeypatch.setattr(stripe_subscriptions, "create", fake_create)
    monkeypatch.setattr(stripe_subscriptions, "cancel", fake_cancel)

    sub = await BillingService.create_subscription(
        db_session, "buyer@example.com", "enterprise"
    )
    await BillingService.cancel_subscription(db_session, sub.id)
    assert cancelled == ["sub_test_123"]
    assert sub.status == "canceled"
    assert sub.canceled_at is not None


@pytest.mark.asyncio
async def test_handle_subscription_deleted_webhook(db_session: AsyncSession, monkeypatch):
    def fake_create(**kwargs):
        return _FakeSubscription("sub_webhook_1")

    monkeypatch.setattr(stripe_subscriptions, "create", fake_create)

    sub = await BillingService.create_subscription(
        db_session, "buyer@example.com", "standard"
    )
    updated = await BillingService.handle_subscription_deleted(
        db_session, {"id": "sub_webhook_1"}
    )
    assert updated is not None
    assert updated.status == "canceled"

    # Unknown subscription id → no-op
    none = await BillingService.handle_subscription_deleted(db_session, {"id": "nope"})
    assert none is None
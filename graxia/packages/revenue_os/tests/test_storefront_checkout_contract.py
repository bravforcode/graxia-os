from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from graxia.services.revenue_os_api.routers import checkout
from graxia.packages.revenue_os.enums import ProductStatus
from graxia.packages.revenue_os.schemas import CheckoutSessionBySlugCreate


class FakeDB:
    def __init__(self, product):
        self.product = product

    async def scalar(self, statement):
        return self.product


@pytest.mark.asyncio
async def test_storefront_checkout_uses_server_product_and_returns_hosted_url(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://shop.example.test")
    monkeypatch.setenv("REVENUE_OS_KILL_SWITCH_FILE", str(tmp_path / "missing.json"))
    product = SimpleNamespace(
        id=uuid4(),
        slug="prompt-pack",
        name="Prompt Pack",
        status=ProductStatus.PUBLISHED,
        price_cents=29900,
        currency="THB",
        stripe_price_id=None,
    )
    calls = {}

    def fake_create(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(id="cs_test_123", url="https://checkout.stripe.test/session")

    monkeypatch.setattr(checkout, "stripe_checkout", SimpleNamespace(create=fake_create))
    response = await checkout.create_checkout_session_by_slug(
        CheckoutSessionBySlugCreate(
            product_slug="prompt-pack",
            success_url="https://shop.example.test/thanks",
            cancel_url="https://shop.example.test/cancel",
        ),
        db=FakeDB(product),
    )
    assert response.checkout_url == "https://checkout.stripe.test/session"
    assert calls["line_items"][0]["price_data"]["unit_amount"] == 29900
    assert calls["metadata"]["product_id"] == str(product.id)


@pytest.mark.asyncio
async def test_storefront_checkout_rejects_unapproved_redirect_origin(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://approved.example.test")
    monkeypatch.setenv("REVENUE_OS_KILL_SWITCH_FILE", str(tmp_path / "missing.json"))
    payload = CheckoutSessionBySlugCreate(
        product_slug="prompt-pack",
        success_url="https://unapproved.example.test/thanks",
        cancel_url="https://approved.example.test/cancel",
    )
    product = SimpleNamespace(
        id=uuid4(),
        slug="prompt-pack",
        name="Prompt Pack",
        status=ProductStatus.PUBLISHED,
        price_cents=29900,
        currency="THB",
        stripe_price_id=None,
    )
    with pytest.raises(HTTPException) as error:
        await checkout.create_checkout_session_by_slug(
            payload,
            db=FakeDB(product),
        )
    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_storefront_checkout_fails_closed_without_production_allowlist(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    monkeypatch.setenv("REVENUE_OS_KILL_SWITCH_FILE", str(tmp_path / "missing.json"))
    payload = CheckoutSessionBySlugCreate(
        product_slug="prompt-pack",
        success_url="https://shop.example.test/thanks",
        cancel_url="https://shop.example.test/cancel",
    )
    product = SimpleNamespace(
        id=uuid4(),
        slug="prompt-pack",
        name="Prompt Pack",
        status=ProductStatus.PUBLISHED,
        price_cents=29900,
        currency="THB",
        stripe_price_id=None,
    )
    with pytest.raises(HTTPException) as error:
        await checkout.create_checkout_session_by_slug(payload, db=FakeDB(product))
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_storefront_checkout_rejects_non_https_provider_url(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("REVENUE_OS_KILL_SWITCH_FILE", str(tmp_path / "missing.json"))
    product = SimpleNamespace(
        id=uuid4(),
        slug="prompt-pack",
        name="Prompt Pack",
        status=ProductStatus.PUBLISHED,
        price_cents=29900,
        currency="THB",
        stripe_price_id=None,
    )
    monkeypatch.setattr(
        checkout,
        "stripe_checkout",
        SimpleNamespace(create=lambda **kwargs: SimpleNamespace(id="cs_test_123", url="http://not-safe")),
    )
    payload = CheckoutSessionBySlugCreate(
        product_slug="prompt-pack",
        success_url="https://shop.example.test/thanks",
        cancel_url="https://shop.example.test/cancel",
    )
    with pytest.raises(HTTPException) as error:
        await checkout.create_checkout_session_by_slug(payload, db=FakeDB(product))
    assert error.value.status_code == 502

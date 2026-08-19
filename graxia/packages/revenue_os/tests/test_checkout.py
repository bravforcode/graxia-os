"""Tests for checkout session creation (P0-1 payment initiation)."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from graxia.services.revenue_os_api.routers.checkout import (
    create_checkout_session,
    stripe_checkout,
)
from ..enums import ProductStatus, ProductType
from ..models import Product
from ..schemas import CheckoutSessionCreate


class _FakeSession:
    def __init__(self, session_id="cs_test_123", url="https://checkout.stripe.com/c/pay/cs_test_123"):
        self.id = session_id
        self.url = url


@pytest.fixture
async def published_product(db_session: AsyncSession) -> Product:
    product = Product(
        name="Test Product",
        slug="test-product-checkout",
        type=ProductType.LOW_TICKET,
        price_cents=9900,
        currency="THB",
        status=ProductStatus.PUBLISHED,
    )
    db_session.add(product)
    await db_session.flush()
    return product


@pytest.mark.asyncio
async def test_create_checkout_session_success(
    db_session: AsyncSession, published_product: Product, monkeypatch
):
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return _FakeSession()

    monkeypatch.setattr(stripe_checkout, "create", fake_create)

    payload = CheckoutSessionCreate(
        product_id=published_product.id,
        customer_email="buyer@example.com",
        success_url="https://example.com/success",
        cancel_url="https://example.com/cancel",
    )
    resp = await create_checkout_session(payload, db_session)

    assert resp.session_id == "cs_test_123"
    assert resp.checkout_url.startswith("https://checkout.stripe.com")
    # Amount/currency come from DB product, not client
    assert captured["line_items"][0]["price_data"]["unit_amount"] == 9900
    assert captured["line_items"][0]["price_data"]["currency"] == "thb"
    # metadata.product_id set so webhook can create order idempotently
    assert captured["metadata"]["product_id"] == str(published_product.id)
    assert captured["customer_email"] == "buyer@example.com"


@pytest.mark.asyncio
async def test_create_checkout_session_product_not_found(db_session: AsyncSession):
    from uuid import uuid4

    payload = CheckoutSessionCreate(
        product_id=uuid4(),
        customer_email="buyer@example.com",
        success_url="https://example.com/success",
        cancel_url="https://example.com/cancel",
    )
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await create_checkout_session(payload, db_session)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_create_checkout_session_unpublished(db_session: AsyncSession):
    from fastapi import HTTPException

    product = Product(
        name="Draft Product",
        slug="draft-product-checkout",
        type=ProductType.LOW_TICKET,
        price_cents=9900,
        currency="THB",
        status=ProductStatus.IDEA,
    )
    db_session.add(product)
    await db_session.flush()

    payload = CheckoutSessionCreate(
        product_id=product.id,
        customer_email="buyer@example.com",
        success_url="https://example.com/success",
        cancel_url="https://example.com/cancel",
    )
    with pytest.raises(HTTPException) as exc:
        await create_checkout_session(payload, db_session)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_create_checkout_session_no_price(db_session: AsyncSession):
    from fastapi import HTTPException

    product = Product(
        name="Free Product",
        slug="free-product-checkout",
        type=ProductType.LEAD_MAGNET,
        price_cents=0,
        currency="THB",
        status=ProductStatus.PUBLISHED,
    )
    db_session.add(product)
    await db_session.flush()

    payload = CheckoutSessionCreate(
        product_id=product.id,
        customer_email="buyer@example.com",
        success_url="https://example.com/success",
        cancel_url="https://example.com/cancel",
    )
    with pytest.raises(HTTPException) as exc:
        await create_checkout_session(payload, db_session)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_create_checkout_session_stripe_error(
    db_session: AsyncSession, published_product: Product, monkeypatch
):
    from fastapi import HTTPException
    import stripe

    def fake_create(**kwargs):
        raise stripe.error.StripeError("boom")

    monkeypatch.setattr(stripe_checkout, "create", fake_create)

    payload = CheckoutSessionCreate(
        product_id=published_product.id,
        customer_email="buyer@example.com",
        success_url="https://example.com/success",
        cancel_url="https://example.com/cancel",
    )
    with pytest.raises(HTTPException) as exc:
        await create_checkout_session(payload, db_session)
    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_create_checkout_session_subscription_mode(
    db_session: AsyncSession, published_product: Product, monkeypatch
):
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return _FakeSession()

    monkeypatch.setattr(stripe_checkout, "create", fake_create)

    payload = CheckoutSessionCreate(
        product_id=published_product.id,
        customer_email="buyer@example.com",
        success_url="https://example.com/success",
        cancel_url="https://example.com/cancel",
        mode="subscription",
    )
    resp = await create_checkout_session(payload, db_session)

    assert resp.session_id == "cs_test_123"
    assert captured["mode"] == "subscription"
    assert captured["line_items"][0]["price_data"]["recurring"] == {"interval": "month"}
    assert captured["metadata"]["mode"] == "subscription"


@pytest.mark.asyncio
async def test_create_checkout_session_uses_stripe_price_id(
    db_session: AsyncSession, published_product: Product, monkeypatch
):
    published_product.stripe_price_id = "price_123"
    await db_session.flush()
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return _FakeSession()

    monkeypatch.setattr(stripe_checkout, "create", fake_create)

    payload = CheckoutSessionCreate(
        product_id=published_product.id,
        customer_email="buyer@example.com",
        success_url="https://example.com/success",
        cancel_url="https://example.com/cancel",
    )
    await create_checkout_session(payload, db_session)

    assert captured["line_items"][0]["price"] == "price_123"
    assert "price_data" not in captured["line_items"][0]


@pytest.mark.asyncio
async def test_create_checkout_session_rejects_invalid_mode(
    db_session: AsyncSession, published_product: Product
):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CheckoutSessionCreate(
            product_id=published_product.id,
            customer_email="buyer@example.com",
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
            mode="bogus",
        )
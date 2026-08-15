import uuid
from datetime import datetime, timedelta
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..celery.tasks.digital_fulfillment import sweep_pending_fulfillments, digital_fulfillment_with_db
from ..enums import DeliveryStatus, OrderStatus, ProductStatus
from ..models import AutomationLock, Customer, DeliveryEvent, Order, Product
from ..services.fulfillment_service import FulfillmentService
from ..services.order_service import OrderService
from ..services.webhook_processor import WebhookProcessor


async def _make_product(db: AsyncSession, data: dict) -> Product:
    product = Product(
        name=data["name"],
        slug=data["slug"],
        price_cents=data["price_cents"],
        status=ProductStatus.PUBLISHED,
        fulfillment_url="https://example.com/access",
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


async def _make_customer(db: AsyncSession, data: dict) -> Customer:
    customer = Customer(email=data["email"], name=data["name"], total_spent_cents=0)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return customer


@pytest.mark.asyncio
async def test_webhook_fulfills_digital_order(db_session: AsyncSession, sample_product_data, sample_customer_data):
    product = await _make_product(db_session, sample_product_data)
    order = await WebhookProcessor.process_stripe_checkout_completed(
        {
            "id": "cs_test_1",
            "customer_email": sample_customer_data["email"],
            "customer_name": sample_customer_data["name"],
            "amount_total": product.price_cents,
            "currency": "thb",
            "payment_intent": "pi_test_1",
            "metadata": {"product_id": str(product.id)},
        },
        db_session,
    )
    assert order is not None
    assert order.status == OrderStatus.PAID
    delivery = await db_session.scalar(
        select(DeliveryEvent).where(DeliveryEvent.order_id == order.id)
    )
    assert delivery is not None
    assert delivery.status == DeliveryStatus.QUEUED


@pytest.mark.asyncio
async def test_webhook_duplicate_is_idempotent(db_session: AsyncSession, sample_product_data, sample_customer_data):
    product = await _make_product(db_session, sample_product_data)
    payload = {
        "id": "cs_test_dup",
        "customer_email": sample_customer_data["email"],
        "amount_total": product.price_cents,
        "currency": "thb",
        "payment_intent": "pi_test_dup",
        "metadata": {"product_id": str(product.id)},
    }
    first = await WebhookProcessor.process_stripe_checkout_completed(payload, db_session)
    second = await WebhookProcessor.process_stripe_checkout_completed(payload, db_session)
    assert second is None  # already processed
    orders = (await db_session.execute(select(Order))).scalars().all()
    assert len(orders) == 1
    deliveries = (await db_session.execute(select(DeliveryEvent))).scalars().all()
    assert len(deliveries) == 1  # no duplicate delivery/email


@pytest.mark.asyncio
async def test_sweep_fulfills_stuck_paid_orders(db_session: AsyncSession, sample_product_data, sample_customer_data):
    product = await _make_product(db_session, sample_product_data)
    order = await OrderService.create_order(
        db_session,
        platform="stripe",
        platform_order_id="cs_stuck_1",
        customer_email=sample_customer_data["email"],
        product_id=product.id,
        amount_cents=product.price_cents,
    )
    await OrderService.update_order_status(db_session, order.id, OrderStatus.PAID)
    fulfilled = await sweep_pending_fulfillments(db_session)
    assert fulfilled == 1
    delivery = await db_session.scalar(
        select(DeliveryEvent).where(DeliveryEvent.order_id == order.id)
    )
    assert delivery is not None


@pytest.mark.asyncio
async def test_sweep_is_idempotent(db_session: AsyncSession, sample_product_data, sample_customer_data):
    product = await _make_product(db_session, sample_product_data)
    await WebhookProcessor.process_stripe_checkout_completed(
        {
            "id": "cs_test_2",
            "customer_email": sample_customer_data["email"],
            "amount_total": product.price_cents,
            "currency": "thb",
            "payment_intent": "pi_test_2",
            "metadata": {"product_id": str(product.id)},
        },
        db_session,
    )
    assert await sweep_pending_fulfillments(db_session) == 0  # already fulfilled


@pytest.mark.asyncio
async def test_sweep_respects_automation_lock(db_session: AsyncSession):
    """Risk Audit #8: the wrapper must skip when another worker holds the lock."""
    # Pre-acquire the lock row so acquire_automation_lock reports it as held.
    db_session.add(AutomationLock(
        name="digital_fulfillment",
        owner="other-worker",
        locked_by_worker="other-worker",
        locked_until=datetime.utcnow() + timedelta(minutes=5),
    ))
    await db_session.commit()
    result = await digital_fulfillment_with_db(db_session)
    assert result.get("skipped") is True
    assert "lock" in result.get("reason", "")

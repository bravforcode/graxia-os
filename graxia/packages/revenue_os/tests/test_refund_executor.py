import uuid
from datetime import datetime, timedelta
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..services.refund_executor import RefundExecutor
from ..enums import OrderStatus, RefundStatus
from ..models import Order, Refund
from ..services.order_service import OrderService


@pytest.mark.asyncio
async def test_stripe_refund_calls_api_and_marks_processed(db_session: AsyncSession, sample_product_data, sample_customer_data, monkeypatch):
    from ..models import Product, ProductStatus
    product = Product(name=sample_product_data["name"], slug=sample_product_data["slug"],
                      price_cents=sample_product_data["price_cents"], status=ProductStatus.PUBLISHED)
    db_session.add(product)
    await db_session.commit()
    order = await OrderService.create_order(
        db_session, platform="stripe", platform_order_id="cs_ref_1",
        customer_email=sample_customer_data["email"], product_id=product.id,
        amount_cents=500_00, stripe_payment_intent="pi_ref_1",
    )
    await OrderService.update_order_status(db_session, order.id, OrderStatus.PAID)
    refund = Refund(order_id=order.id, amount_cents=500_00, currency="THB",
                    reason="test", status=RefundStatus.PROCESSING, platform="stripe")
    db_session.add(refund)
    await db_session.commit()

    class FakeStripeRefunds:
        @staticmethod
        def create(**kwargs):
            assert kwargs["payment_intent"] == "pi_ref_1"
            assert kwargs["amount"] == 500_00
            return type("R", (), {"id": "re_fake_1"})()

    monkeypatch.setattr("graxia.packages.revenue_os.services.refund_executor.stripe_refunds", FakeStripeRefunds)
    result = await RefundExecutor.process_pending_refunds(db_session)
    assert result["processed"] == 1
    await db_session.refresh(refund)
    assert refund.status == RefundStatus.PROCESSED
    assert refund.platform_refund_id == "re_fake_1"


@pytest.mark.asyncio
async def test_failed_refund_marked_failed(db_session: AsyncSession, sample_product_data, sample_customer_data, monkeypatch):
    from ..models import Product, ProductStatus
    product = Product(name=sample_product_data["name"], slug=sample_product_data["slug"],
                      price_cents=sample_product_data["price_cents"], status=ProductStatus.PUBLISHED)
    db_session.add(product)
    await db_session.commit()
    order = await OrderService.create_order(
        db_session, platform="stripe", platform_order_id="cs_ref_2",
        customer_email=sample_customer_data["email"], product_id=product.id,
        amount_cents=500_00, stripe_payment_intent="pi_ref_2",
    )
    await OrderService.update_order_status(db_session, order.id, OrderStatus.PAID)
    refund = Refund(order_id=order.id, amount_cents=500_00, currency="THB",
                    reason="test", status=RefundStatus.PROCESSING, platform="stripe")
    db_session.add(refund)
    await db_session.commit()

    class Boom:
        @staticmethod
        def create(**kwargs):
            raise Exception("card declined")

    monkeypatch.setattr("graxia.packages.revenue_os.services.refund_executor.stripe_refunds", Boom)
    result = await RefundExecutor.process_pending_refunds(db_session)
    assert result["failed"] == 1
    await db_session.refresh(refund)
    assert refund.status == RefundStatus.FAILED


@pytest.mark.asyncio
async def test_non_stripe_refund_skipped(db_session: AsyncSession, sample_product_data, sample_customer_data):
    from ..models import Product, ProductStatus
    product = Product(name=sample_product_data["name"], slug=sample_product_data["slug"],
                      price_cents=sample_product_data["price_cents"], status=ProductStatus.PUBLISHED)
    db_session.add(product)
    await db_session.commit()
    order = await OrderService.create_order(
        db_session, platform="manual", platform_order_id="cs_ref_3",
        customer_email=sample_customer_data["email"], product_id=product.id,
        amount_cents=500_00,
    )
    await OrderService.update_order_status(db_session, order.id, OrderStatus.PAID)
    refund = Refund(order_id=order.id, amount_cents=500_00, currency="THB",
                    reason="test", status=RefundStatus.PROCESSING, platform="manual")
    db_session.add(refund)
    await db_session.commit()
    result = await RefundExecutor.process_pending_refunds(db_session)
    assert result["skipped"] == 1
    assert result["processed"] == 0

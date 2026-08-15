import uuid
from datetime import datetime, timedelta
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.support import SupportAgent
from ..core.policy_engine import PolicyEngine
from ..enums import OrderStatus, RefundStatus, SupportIntent
from ..models import IncidentEvent, Order, Refund, SupportVerification


@pytest.mark.asyncio
async def test_classify_wismo_thai():
    assert SupportAgent.classify_intent("ออเดอร์ของฉันอยู่ไหน ส่งของหรือยัง") == SupportIntent.WISMO


@pytest.mark.asyncio
async def test_classify_refund_english():
    assert SupportAgent.classify_intent("I want a refund please") == SupportIntent.REFUND


@pytest.mark.asyncio
async def test_classify_product_question():
    assert SupportAgent.classify_intent("สินค้านี้เหมาะกับมือใหม่ไหม") == SupportIntent.PRODUCT_QUESTION


@pytest.mark.asyncio
async def test_wismo_requires_verification_code(db_session: AsyncSession):
    reply = await SupportAgent.handle_message(db_session, "where is my order?", "nobody@example.com")
    assert reply.action_taken == "verification_required"
    ver = await db_session.scalar(select(SupportVerification).where(
        SupportVerification.email == "nobody@example.com"))
    assert ver is not None


@pytest.mark.asyncio
async def test_wismo_with_code_replies_status(db_session: AsyncSession, sample_product_data, sample_customer_data):
    from ..models import Product, ProductStatus
    product = Product(name=sample_product_data["name"], slug=sample_product_data["slug"],
                      price_cents=sample_product_data["price_cents"], status=ProductStatus.PUBLISHED)
    db_session.add(product)
    await db_session.commit()
    from ..services.order_service import OrderService
    order = await OrderService.create_order(
        db_session, platform="stripe", platform_order_id="wismo_1",
        customer_email=sample_customer_data["email"], product_id=product.id, amount_cents=9900,
    )
    code = await SupportAgent._issue_verification_code(db_session, order.customer_email)
    reply = await SupportAgent.handle_message(
        db_session, "where is my order?", order.customer_email, verification_code=code)
    assert reply.action_taken == "wismo"
    assert order.status.value in reply.text.lower()


@pytest.mark.asyncio
async def test_wrong_code_escalates_after_attempts(db_session: AsyncSession):
    await SupportAgent._issue_verification_code(db_session, "nobody@example.com")
    for _ in range(5):
        reply = await SupportAgent.handle_message(
            db_session, "where is my order?", "nobody@example.com", verification_code="000000")
        assert reply.action_taken in ("verification_failed", "verification_exhausted")
    incident = await db_session.scalar(select(IncidentEvent).order_by(IncidentEvent.created_at.desc()))
    assert incident is not None


@pytest.mark.asyncio
async def test_refund_within_policy_creates_refund(db_session: AsyncSession, sample_product_data, sample_customer_data):
    await PolicyEngine.seed_default_rules(db_session)
    from ..models import Product, ProductStatus
    product = Product(name=sample_product_data["name"], slug=sample_product_data["slug"],
                      price_cents=sample_product_data["price_cents"], status=ProductStatus.PUBLISHED)
    db_session.add(product)
    await db_session.commit()
    from ..services.order_service import OrderService
    order = await OrderService.create_order(
        db_session, platform="stripe", platform_order_id="ref_ok_1",
        customer_email=sample_customer_data["email"], product_id=product.id, amount_cents=500_00,
    )
    order.status = OrderStatus.PAID
    order.purchased_at = datetime.utcnow() - timedelta(days=2)
    await db_session.commit()
    code = await SupportAgent._issue_verification_code(db_session, order.customer_email)
    reply = await SupportAgent.handle_message(
        db_session, "please refund me", order.customer_email, verification_code=code)
    assert reply.action_taken == "refund"
    refund = await db_session.scalar(select(Refund).where(Refund.order_id == order.id))
    assert refund is not None
    assert refund.status == RefundStatus.PROCESSING


@pytest.mark.asyncio
async def test_refund_duplicate_message_is_idempotent(db_session: AsyncSession, sample_product_data, sample_customer_data):
    """Risk Audit #4: repeating the same refund request must not create a second Refund."""
    await PolicyEngine.seed_default_rules(db_session)
    from ..models import Product, ProductStatus
    product = Product(name=sample_product_data["name"], slug=sample_product_data["slug"],
                      price_cents=sample_product_data["price_cents"], status=ProductStatus.PUBLISHED)
    db_session.add(product)
    await db_session.commit()
    from ..services.order_service import OrderService
    order = await OrderService.create_order(
        db_session, platform="stripe", platform_order_id="ref_dup_1",
        customer_email=sample_customer_data["email"], product_id=product.id, amount_cents=500_00,
    )
    order.status = OrderStatus.PAID
    order.purchased_at = datetime.utcnow() - timedelta(days=2)
    await db_session.commit()
    code = await SupportAgent._issue_verification_code(db_session, order.customer_email)
    await SupportAgent.handle_message(db_session, "refund me", order.customer_email, verification_code=code)
    code2 = await SupportAgent._issue_verification_code(db_session, order.customer_email)
    reply2 = await SupportAgent.handle_message(db_session, "refund me", order.customer_email, verification_code=code2)
    assert reply2.action_taken == "refund_duplicate"
    refunds = (await db_session.execute(select(Refund).where(Refund.order_id == order.id))).scalars().all()
    assert len(refunds) == 1


@pytest.mark.asyncio
async def test_refund_above_absolute_cap_escalates(db_session: AsyncSession, sample_product_data, sample_customer_data):
    await PolicyEngine.seed_default_rules(db_session)
    from ..models import Product, ProductStatus
    product = Product(name=sample_product_data["name"], slug=sample_product_data["slug"],
                      price_cents=sample_product_data["price_cents"], status=ProductStatus.PUBLISHED)
    db_session.add(product)
    await db_session.commit()
    from ..services.order_service import OrderService
    order = await OrderService.create_order(
        db_session, platform="stripe", platform_order_id="ref_big_1",
        customer_email=sample_customer_data["email"], product_id=product.id, amount_cents=10_000_00,
    )
    order.status = OrderStatus.PAID
    order.purchased_at = datetime.utcnow() - timedelta(days=2)
    await db_session.commit()
    code = await SupportAgent._issue_verification_code(db_session, order.customer_email)
    reply = await SupportAgent.handle_message(
        db_session, "please refund me", order.customer_email, verification_code=code)
    assert reply.action_taken == "refund_escalated"
    incident = await db_session.scalar(select(IncidentEvent).order_by(IncidentEvent.created_at.desc()))
    assert incident is not None


@pytest.mark.asyncio
async def test_refund_old_order_denied(db_session: AsyncSession, sample_product_data, sample_customer_data):
    await PolicyEngine.seed_default_rules(db_session)
    from ..models import Product, ProductStatus
    product = Product(name=sample_product_data["name"], slug=sample_product_data["slug"],
                      price_cents=sample_product_data["price_cents"], status=ProductStatus.PUBLISHED)
    db_session.add(product)
    await db_session.commit()
    from ..services.order_service import OrderService
    order = await OrderService.create_order(
        db_session, platform="stripe", platform_order_id="ref_old_1",
        customer_email=sample_customer_data["email"], product_id=product.id, amount_cents=500_00,
    )
    order.status = OrderStatus.PAID
    order.purchased_at = datetime.utcnow() - timedelta(days=60)
    await db_session.commit()
    code = await SupportAgent._issue_verification_code(db_session, order.customer_email)
    reply = await SupportAgent.handle_message(
        db_session, "please refund me", order.customer_email, verification_code=code)
    assert reply.action_taken == "refund_denied"

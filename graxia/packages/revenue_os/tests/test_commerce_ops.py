import uuid
from datetime import datetime, timedelta
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.commerce_ops import CommerceOpsAgent
from ..core.policy_engine import PolicyEngine
from ..enums import AutonomyMode, IncidentSeverity, OrderStatus, ProductStatus
from ..models import AuditLog, IncidentEvent, Product, StrategyLog
from ..services.campaign_service import RevenueCampaignService


@pytest.mark.asyncio
async def test_run_cycle_skips_when_off(db_session: AsyncSession):
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.OFF)
    result = await CommerceOpsAgent.run_cycle(db_session)
    assert result["skipped"] is True


@pytest.mark.asyncio
async def test_price_cut_for_stale_product(db_session: AsyncSession, sample_product_data):
    await PolicyEngine.seed_default_rules(db_session)
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.FULL)
    product = Product(
        name=sample_product_data["name"],
        slug=sample_product_data["slug"],
        price_cents=sample_product_data["price_cents"],
        status=ProductStatus.PUBLISHED,
        created_at=datetime.utcnow() - timedelta(days=21),
    )
    db_session.add(product)
    await db_session.commit()
    old_price = product.price_cents

    result = await CommerceOpsAgent.run_cycle(db_session)

    assert any("price" in a.lower() for a in result["actions_taken"])
    await db_session.refresh(product)
    assert product.price_cents < old_price
    assert old_price - product.price_cents <= old_price * 0.2  # within ±20% policy
    log = await db_session.scalar(select(AuditLog).where(AuditLog.event_type == "agent.price_change"))
    assert log is not None


@pytest.mark.asyncio
async def test_price_cut_denied_beyond_policy(db_session: AsyncSession, sample_product_data):
    await PolicyEngine.seed_default_rules(db_session)
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.FULL)
    from ..enums import RuleType
    from ..models import PolicyRule
    db_session.add(PolicyRule(action="price_change", rule_type=RuleType.MAX, value=5.0, priority=500))
    await db_session.commit()

    product = Product(
        name=sample_product_data["name"],
        slug=sample_product_data["slug"],
        price_cents=sample_product_data["price_cents"],
        status=ProductStatus.PUBLISHED,
        created_at=datetime.utcnow() - timedelta(days=21),
    )
    db_session.add(product)
    await db_session.commit()

    result = await CommerceOpsAgent.run_cycle(db_session)
    assert result["policy_denials"], "expected a denial"
    incident = await db_session.scalar(select(IncidentEvent).order_by(IncidentEvent.created_at.desc()))
    assert incident is not None


@pytest.mark.asyncio
async def test_shadow_mode_proposes_but_does_not_execute(db_session: AsyncSession, sample_product_data):
    await PolicyEngine.seed_default_rules(db_session)
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.SHADOW)
    product = Product(
        name=sample_product_data["name"],
        slug=sample_product_data["slug"],
        price_cents=sample_product_data["price_cents"],
        status=ProductStatus.PUBLISHED,
        created_at=datetime.utcnow() - timedelta(days=21),
    )
    db_session.add(product)
    await db_session.commit()
    old_price = product.price_cents

    result = await CommerceOpsAgent.run_cycle(db_session)

    assert result["actions_taken"] == []
    assert any("price" in p.lower() for p in result["shadow_proposals"])
    await db_session.refresh(product)
    assert product.price_cents == old_price  # nothing executed


@pytest.mark.asyncio
async def test_stale_pending_order_escalates(db_session: AsyncSession, sample_product_data, sample_customer_data):
    await PolicyEngine.seed_default_rules(db_session)
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.FULL)
    product = Product(
        name=sample_product_data["name"],
        slug=sample_product_data["slug"],
        price_cents=sample_product_data["price_cents"],
        status=ProductStatus.PUBLISHED,
    )
    db_session.add(product)
    await db_session.commit()
    from ..models import Order
    from ..services.order_service import OrderService
    order = await OrderService.create_order(
        db_session,
        platform="stripe",
        platform_order_id="stale_1",
        customer_email=sample_customer_data["email"],
        product_id=product.id,
        amount_cents=9900,
    )
    order.status = OrderStatus.PENDING
    order.created_at = datetime.utcnow() - timedelta(hours=72)
    await db_session.commit()
    result = await CommerceOpsAgent.run_cycle(db_session)
    incident = await db_session.scalar(
        select(IncidentEvent).where(IncidentEvent.severity == IncidentSeverity.LOW)
    )
    assert incident is not None


@pytest.mark.asyncio
async def test_daily_report_writes_strategy_log(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.FULL)
    result = await CommerceOpsAgent.run_cycle(db_session)
    log = await db_session.scalar(select(StrategyLog).order_by(StrategyLog.created_at.desc()))
    assert log is not None
    assert "Daily report" in (log.summary or "")


@pytest.mark.asyncio
async def test_circuit_breaker_blocks_cycle(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.FULL)
    for i in range(5):
        db_session.add(IncidentEvent(title=f"spike {i}", description="x", severity=IncidentSeverity.MEDIUM))
    await db_session.commit()
    result = await CommerceOpsAgent.run_cycle(db_session)
    assert result["skipped"] is True
    assert await PolicyEngine.get_autonomy_mode(db_session) == AutonomyMode.OFF

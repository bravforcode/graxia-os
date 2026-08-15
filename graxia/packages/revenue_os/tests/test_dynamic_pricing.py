from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.policy_engine import PolicyEngine
from ..enums import AutonomyMode, ProductStatus
from ..models import AuditLog, PriceChangeLock, Product
from ..pricing.dynamic import DynamicPricingEngine


def _stale_product(db, data: dict, days: int = 30):
    p = Product(name=data["name"], slug=data["slug"], price_cents=data["price_cents"],
                status=ProductStatus.PUBLISHED, created_at=datetime.utcnow() - timedelta(days=days))
    db.add(p)
    return p


@pytest.mark.asyncio
async def test_propose_stale_cut(db_session: AsyncSession, sample_product_data):
    p = _stale_product(db_session, sample_product_data)
    await db_session.commit()
    delta = await DynamicPricingEngine.propose(db_session, p)
    assert delta == -10.0


@pytest.mark.asyncio
async def test_propose_none_for_new_product(db_session: AsyncSession, sample_product_data):
    p = _stale_product(db_session, sample_product_data, days=1)
    await db_session.commit()
    delta = await DynamicPricingEngine.propose(db_session, p)
    assert delta is None


@pytest.mark.asyncio
async def test_apply_respects_price_change_lock(db_session: AsyncSession, sample_product_data):
    await PolicyEngine.seed_default_rules(db_session)
    p = _stale_product(db_session, sample_product_data)
    await db_session.commit()
    # fresh lock -> rate-limited
    db_session.add(PriceChangeLock(product_id=p.id, last_delta_percent=0.0,
                                   last_change_at=datetime.utcnow()))
    await db_session.commit()
    ok = await DynamicPricingEngine.apply(db_session, p, -10.0)
    assert ok is False
    await db_session.refresh(p)
    assert p.price_cents == sample_product_data["price_cents"]


@pytest.mark.asyncio
async def test_apply_denied_by_tight_policy(db_session: AsyncSession, sample_product_data):
    await PolicyEngine.seed_default_rules(db_session)
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.FULL)
    from ..enums import RuleType
    from ..models import PolicyRule
    db_session.add(PolicyRule(action="price_change", rule_type=RuleType.MAX, value=2.0, priority=500))
    p = _stale_product(db_session, sample_product_data)
    await db_session.commit()
    ok = await DynamicPricingEngine.apply(db_session, p, -10.0)
    assert ok is False  # 10% > 2% cap


@pytest.mark.asyncio
async def test_apply_shadow_logs_without_mutating(db_session: AsyncSession, sample_product_data):
    await PolicyEngine.seed_default_rules(db_session)
    p = _stale_product(db_session, sample_product_data)
    await db_session.commit()
    ok = await DynamicPricingEngine.apply(db_session, p, -10.0, shadow=True)
    assert ok is True
    await db_session.refresh(p)
    assert p.price_cents == sample_product_data["price_cents"]
    log = (await db_session.execute(
        __import__("sqlalchemy").select(AuditLog).where(AuditLog.event_type == "agent.price_change.shadow")
    )).scalars().first()
    assert log is not None

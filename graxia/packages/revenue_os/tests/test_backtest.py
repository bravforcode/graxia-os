import pytest
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.policy_engine import PolicyEngine
from ..enums import AutonomyMode, ProductStatus
from ..models import MetricDaily, Product
from ..simulation.backtest import run_backtest


@pytest.mark.asyncio
async def test_backtest_empty_history_returns_zeros(db_session: AsyncSession):
    report = await run_backtest(db_session, days=30)
    assert report["window_days"] == 30
    assert report["decisions"] == 0
    assert report["est_revenue_impact_cents"] == 0


@pytest.mark.asyncio
async def test_backtest_respects_policy_denies(db_session: AsyncSession, sample_product_data):
    await PolicyEngine.seed_default_rules(db_session)
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.FULL)
    from ..enums import RuleType
    from ..models import PolicyRule
    # tight cap: any -10% proposal denied
    db_session.add(PolicyRule(action="price_change", rule_type=RuleType.MAX, value=2.0, priority=500))
    p = Product(name=sample_product_data["name"], slug=sample_product_data["slug"],
                price_cents=sample_product_data["price_cents"], status=ProductStatus.PUBLISHED,
                created_at=datetime.utcnow() - timedelta(days=30))
    db_session.add(p)
    await db_session.commit()
    report = await run_backtest(db_session, days=30)
    assert report["decisions"] >= 1
    assert report["denied"] >= 1
    # nothing was written to the real product
    await db_session.refresh(p)
    assert p.price_cents == sample_product_data["price_cents"]


@pytest.mark.asyncio
async def test_backtest_estimates_impact_per_action(db_session: AsyncSession, sample_product_data):
    await PolicyEngine.seed_default_rules(db_session)
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.FULL)
    p = Product(name=sample_product_data["name"], slug=sample_product_data["slug"],
                price_cents=sample_product_data["price_cents"], status=ProductStatus.PUBLISHED,
                created_at=datetime.utcnow() - timedelta(days=30))
    db_session.add(p)
    await db_session.commit()
    report = await run_backtest(db_session, days=30)
    assert "price_change" in report["by_action"]
    assert report["by_action"]["price_change"]["allowed"] >= 1
    assert report["by_action"]["price_change"]["denied"] == 0

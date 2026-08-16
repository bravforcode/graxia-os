"""Competitor repricing tests — reaction rule, clamping, shared 24h lock."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.policy_engine import PolicyEngine
from ..enums import ProductStatus
from ..models import AuditLog, PriceChangeLock, Product
from ..pricing.repricing import MAX_REPRICE_PERCENT, repricing_cycle


async def _product(db_session: AsyncSession, price=10000, **kw) -> Product:
    product = Product(name="Test Product", slug=f"slug-{price}-{len(kw)}",
                      price_cents=price, status=ProductStatus.PUBLISHED, **kw)
    db_session.add(product)
    await db_session.commit()
    return product


@pytest.mark.asyncio
async def test_reacts_only_when_above_competitor_plus_buffer(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    expensive = await _product(db_session, price=10000)   # 100 THB
    cheap = await _product(db_session, price=9800)        # 98 THB
    # competitor at 90 THB: expensive is 11% above (reacts), cheap is 8.9%
    # above (reacts? 9800 > 9000*1.05=9450 -> yes reacts). Both > buffer.
    result = await repricing_cycle(db_session, {
        str(expensive.id): 9000,
        str(cheap.id): 9000,
    })
    assert result["applied"] == 2
    # at/below competitor + 5% buffer -> no reaction
    at_price = await _product(db_session, price=9400)  # 9400 <= 9000*1.05=9450
    result2 = await repricing_cycle(db_session, {str(at_price.id): 9000})
    assert result2 == {"applied": 0, "skipped": 1, "changes": []}


@pytest.mark.asyncio
async def test_delta_clamped_to_max_repricing_percent(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    product = await _product(db_session, price=10000)
    # competitor 20 THB -> desired 19.6 THB -> delta -80% clamped to -20%
    result = await repricing_cycle(db_session, {str(product.id): 2000})
    assert result["applied"] == 1
    assert result["changes"][0]["delta_percent"] == -MAX_REPRICE_PERCENT
    await db_session.refresh(product)
    assert product.price_cents == 8000  # -20% of 10000


@pytest.mark.asyncio
async def test_retargets_to_2_percent_under_competitor(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    product = await _product(db_session, price=10000)
    # competitor 95 THB -> desired 93.1 THB -> delta -6.9%
    result = await repricing_cycle(db_session, {str(product.id): 9500})
    assert result["changes"][0]["delta_percent"] == -6.9
    await db_session.refresh(product)
    assert product.price_cents == 9310


@pytest.mark.asyncio
async def test_24h_lock_blocks_repeated_cycle(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    product = await _product(db_session, price=10000)
    db_session.add(PriceChangeLock(product_id=product.id, last_delta_percent=0.0))
    await db_session.commit()  # fresh lock -> within 24h window
    result = await repricing_cycle(db_session, {str(product.id): 9000})
    assert result["applied"] == 0  # shared 24h lock applies
    assert result["skipped"] == 1
    await db_session.refresh(product)
    assert product.price_cents == 10000  # untouched


@pytest.mark.asyncio
async def test_fails_closed_without_policy_rules(db_session: AsyncSession):
    # no seeded PRICE_CHANGE rules -> policy denies -> nothing applied
    product = await _product(db_session, price=10000)
    result = await repricing_cycle(db_session, {str(product.id): 9000})
    assert result["applied"] == 0
    assert result["skipped"] == 1
    await db_session.refresh(product)
    assert product.price_cents == 10000


@pytest.mark.asyncio
async def test_apply_writes_audit_log(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    product = await _product(db_session, price=10000)
    await repricing_cycle(db_session, {str(product.id): 9000})
    logs = (await db_session.execute(select(AuditLog).where(
        AuditLog.event_type == "agent.price_change.dynamic"))).scalars().all()
    assert len(logs) == 1
    assert logs[0].metadata_["product_id"] == str(product.id)

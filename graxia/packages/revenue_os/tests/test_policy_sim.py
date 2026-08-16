"""Policy scenario simulation tests — pure read, engine-faithful evaluation."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.policy_engine import PolicyEngine
from ..core.policy_sim import simulate_policy_change
from ..enums import OrderStatus, ProductStatus
from ..models import Order, PolicyRule, Product


async def _order(db_session: AsyncSession, oid: str, amount: int, cost: int):
    product = Product(name="Test Product", slug=f"sim-{oid}",
                      price_cents=amount, status=ProductStatus.PUBLISHED,
                      supplier="printful", supplier_cost_cents=cost, is_physical=True)
    db_session.add(product)
    await db_session.commit()
    from ..services.order_service import OrderService
    order = await OrderService.create_order(
        db_session, platform="shopee", platform_order_id=oid,
        customer_email="c@example.com", product_id=product.id, amount_cents=amount,
    )
    order.status = OrderStatus.PAID
    order.purchased_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db_session.commit()
    return order


@pytest.mark.asyncio
async def test_simulation_denies_low_margin_orders(db_session: AsyncSession):
    await PolicyEngine.set_autonomy_mode(db_session, "full")
    high = await _order(db_session, "sim_high", 9900, 3000)  # margin 69.7%
    low = await _order(db_session, "sim_low", 9900, 9000)    # margin 9.1%
    result = await simulate_policy_change(
        db_session, "supplier_purchase",
        [("min", "percent", 50.0), ("max", "absolute", 100_000_00)])
    assert result["supported"] is True
    assert result["orders_checked"] == 2
    assert result["would_allow"] == 1   # high-margin order
    assert result["would_deny"] == 1    # low-margin order
    assert "below min" in result["denied_examples"][0]["reason"]
    # pure read: nothing persisted
    rules = await db_session.scalar(select(func.count(PolicyRule.id)))
    assert rules == 0
    orders = await db_session.scalar(select(func.count(Order.id)))
    assert orders == 2


@pytest.mark.asyncio
async def test_simulation_fails_closed_without_applicable_rule(db_session: AsyncSession):
    await PolicyEngine.set_autonomy_mode(db_session, "full")
    await _order(db_session, "sim_nc", 9900, 3000)
    result = await simulate_policy_change(db_session, "supplier_purchase", [])
    assert result["would_deny"] == 1  # no applicable rule -> deny (like check())
    assert "no applicable rule" in result["denied_examples"][0]["reason"]


@pytest.mark.asyncio
async def test_simulation_unsupported_action(db_session: AsyncSession):
    result = await simulate_policy_change(db_session, "affiliate", [("max", "percent", 20.0)])
    assert result["supported"] is False

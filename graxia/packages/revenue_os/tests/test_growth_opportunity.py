"""Growth opportunity tests — margin shift, demand, low-margin, digest."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ..enums import ChannelType, ProductStatus
from ..growth.opportunity import _digest_text, opportunity_scan
from ..models import ChannelConnection, Product


_slug_seq = {"n": 0}


async def _order(db_session: AsyncSession, platform: str, amount: int,
                 cost: int, days_ago: int = 1):
    from datetime import datetime, timedelta, timezone
    _slug_seq["n"] += 1
    product = Product(name="Test Product", slug=f"g-{_slug_seq['n']}",
                      price_cents=amount, status=ProductStatus.PUBLISHED,
                      supplier="printful", supplier_cost_cents=cost, is_physical=True)
    db_session.add(product)
    await db_session.commit()
    from ..services.order_service import OrderService
    order = await OrderService.create_order(
        db_session, platform=platform, platform_order_id=f"g-{platform}-{amount}",
        customer_email="c@example.com", product_id=product.id, amount_cents=amount,
    )
    from ..enums import OrderStatus
    order.status = OrderStatus.PAID
    order.purchased_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    await db_session.commit()
    return order


@pytest.mark.asyncio
async def test_opportunity_scan_margin_shift_and_demand(db_session: AsyncSession):
    # shopee: high margin (cost low); amazon: negative margin (cost high)
    await _order(db_session, "shopee", 10000, 1000)
    await _order(db_session, "shopee", 10000, 1000)
    await _order(db_session, "amazon", 10000, 9500)
    scan = await opportunity_scan(db_session)
    types = {r["type"] for r in scan["recommendations"]}
    assert "channel_margin_shift" in types
    shift = next(r for r in scan["recommendations"] if r["type"] == "channel_margin_shift")
    assert shift["to"] == "shopee"  # higher margin wins
    assert "channel_demand" in types
    demand = [r for r in scan["recommendations"] if r["type"] == "channel_demand"]
    assert {r["channel"] for r in demand} == {"shopee", "amazon"}


@pytest.mark.asyncio
async def test_opportunity_scan_low_margin_channel(db_session: AsyncSession):
    await _order(db_session, "amazon", 10000, 9500)  # margin ~ -5% < 20%
    scan = await opportunity_scan(db_session)
    low = [r for r in scan["recommendations"] if r["type"] == "low_margin_channel"]
    assert any(r["channel"] == "amazon" for r in low)


@pytest.mark.asyncio
async def test_opportunity_scan_empty_db(db_session: AsyncSession):
    scan = await opportunity_scan(db_session)
    assert scan["recommendations"] == []


@pytest.mark.asyncio
async def test_digest_text_renders(db_session: AsyncSession):
    await _order(db_session, "shopee", 10000, 1000)
    scan = await opportunity_scan(db_session)
    text = _digest_text(scan)
    assert text.startswith("Growth digest")
    assert "shopee" in text

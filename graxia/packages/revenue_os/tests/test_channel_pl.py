"""Channel P&L tests — revenue/fee/COGS/margin per platform."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ..enums import ChannelType, OrderStatus, ProductStatus
from ..finance.channel_pl import channel_pl
from ..models import ChannelConnection, Order, Product


async def _product(db_session: AsyncSession, cost=3000) -> Product:
    product = Product(name="Test Product", slug="test-product",
                      price_cents=9900, status=ProductStatus.PUBLISHED,
                      supplier="printful", supplier_cost_cents=cost, is_physical=True)
    db_session.add(product)
    await db_session.commit()
    return product


_seq = {"n": 0}


async def _order(db_session: AsyncSession, product, platform, amount, status=OrderStatus.PAID):
    _seq["n"] += 1
    from ..services.order_service import OrderService
    order = await OrderService.create_order(
        db_session, platform=platform, platform_order_id=f"{platform}-{_seq['n']}-{amount}",
        customer_email="c@example.com", product_id=product.id, amount_cents=amount,
    )
    if status != OrderStatus.PAID:
        order.status = status
        await db_session.commit()
    return order


@pytest.mark.asyncio
async def test_channel_pl_per_platform_with_fee_override(db_session: AsyncSession):
    product = await _product(db_session, cost=3000)
    await _order(db_session, product, "shopee", 9900)
    await _order(db_session, product, "shopee", 9900)
    await _order(db_session, product, "amazon", 10000)
    # amazon default fee 0.15; shopee config override 0.10
    db_session.add(ChannelConnection(channel=ChannelType.SHOPEE, name="shopee-store",
                                     config={"fee_rate": 0.10}))
    await db_session.commit()

    rows = {r["platform"]: r for r in await channel_pl(db_session)}
    shopee = rows["shopee"]
    assert shopee["orders"] == 2
    assert shopee["revenue_cents"] == 19800
    assert shopee["est_fee_cents"] == 1980  # 19800 * 0.10
    assert shopee["est_cost_cents"] == 6000
    assert shopee["est_margin_cents"] == 19800 - 1980 - 6000
    amazon = rows["amazon"]
    assert amazon["est_fee_cents"] == 1500  # 10000 * 0.15 default


@pytest.mark.asyncio
async def test_channel_pl_ignores_refunded_and_cancelled(db_session: AsyncSession):
    product = await _product(db_session)
    await _order(db_session, product, "shopee", 9900)  # PAID -> counted
    refunded = await _order(db_session, product, "shopee", 9900)
    refunded.status = OrderStatus.REFUNDED
    await db_session.commit()
    rows = {r["platform"]: r for r in await channel_pl(db_session)}
    assert rows["shopee"]["orders"] == 1
    assert rows["shopee"]["revenue_cents"] == 9900


@pytest.mark.asyncio
async def test_channel_pl_empty_db_returns_empty(db_session: AsyncSession):
    assert await channel_pl(db_session) == []

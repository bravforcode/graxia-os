"""Marketplace sync tests — buffers never negative, fee-aware margin, FX refresh,
price sync respects the 24h lock."""
import pytest
from httpx import AsyncClient, MockTransport, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..channels.marketplace_sync import (
    fee_rate_for,
    fx_refresh,
    inventory_reconcile,
    margin_after_fee,
    price_sync,
)
from ..channels.supplier_pod import SupplierPODAdapter
from ..core.policy_engine import PolicyEngine
from ..enums import AutonomyMode, ChannelType, ProductStatus
from ..models import ChannelConnection, ChannelInventory, PriceChangeLock, Product

LATEST_URL = "https://open.er-api.com/v6/latest/THB"


async def _product(db_session: AsyncSession, currency="THB", price=9900) -> Product:
    product = Product(name="Test Product", slug=f"test-{currency}",
                      price_cents=price, currency=currency, status=ProductStatus.PUBLISHED,
                      supplier="printful", supplier_cost_cents=3000, is_physical=True)
    db_session.add(product)
    await db_session.commit()
    return product


async def _order(db_session: AsyncSession, product, platform="shopee", amount=9900):
    from ..services.order_service import OrderService
    return await OrderService.create_order(
        db_session, platform=platform, platform_order_id=f"o-{amount}",
        customer_email="c@example.com", product_id=product.id, amount_cents=amount,
    )


# ── inventory buffer math (never negative) ───────────────────────────────────

@pytest.mark.asyncio
async def test_buffer_math_never_negative(db_session: AsyncSession):
    product = await _product(db_session)
    rows = [
        ChannelInventory(channel=ChannelType.SHOPEE, product_id=product.id,
                         channel_stock=1, stock_buffer=5),   # 1-5 -> 0, not -4
        ChannelInventory(channel=ChannelType.LAZADA, product_id=product.id,
                         channel_stock=0, stock_buffer=3),   # 0-3 -> 0
        ChannelInventory(channel=ChannelType.AMAZON, product_id=product.id,
                         channel_stock=10, stock_buffer=3),  # 10-3 -> 7
    ]
    db_session.add_all(rows)
    await db_session.commit()

    result = await inventory_reconcile(db_session)
    assert result["rows"] == 3
    avail = result["available"]
    values = list(avail.values())
    assert all(v >= 0 for v in values)  # gate: never negative
    assert avail[f"{ChannelType.SHOPEE.value}:{product.id}"] == 0
    assert avail[f"{ChannelType.AMAZON.value}:{product.id}"] == 7
    assert result["changed"] == 2  # shopee + lazada differ from raw stock


@pytest.mark.asyncio
async def test_inventory_reconcile_pushes_via_adapter(db_session: AsyncSession):
    product = await _product(db_session)
    db_session.add(ChannelInventory(channel=ChannelType.SHOPEE, product_id=product.id,
                                    channel_stock=10, stock_buffer=3))
    await db_session.commit()
    calls = {"n": 0}

    class _FakeAdapter:
        async def sync_products(self):
            calls["n"] += 1
            return 1

    result = await inventory_reconcile(db_session, adapter=_FakeAdapter())
    assert result["changed"] == 1
    assert calls["n"] == 1 and result["pushed"] == 1


# ── fee-aware margin gate ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_margin_after_fee_uses_config_override(db_session: AsyncSession):
    product = await _product(db_session)
    order = await _order(db_session, product, platform="shopee")
    # default shopee fee 0.07: (9900 - 3000 - 693) / 9900
    m = await margin_after_fee(db_session, order, product)
    assert round(m, 4) == round((9900 - 3000 - 9900 * 0.07) / 9900, 4)
    # config override: fee_rate 0.5 -> (9900 - 3000 - 4950) / 9900
    db_session.add(ChannelConnection(channel=ChannelType.SHOPEE, name="shopee-store",
                                     config={"fee_rate": 0.5}))
    await db_session.commit()
    m2 = await margin_after_fee(db_session, order, product)
    assert round(m2, 4) == round((9900 - 3000 - 4950) / 9900, 4)


@pytest.mark.asyncio
async def test_default_fee_rates_per_platform(db_session: AsyncSession):
    product = await _product(db_session)
    assert await fee_rate_for(db_session, "shopee") == 0.07
    assert await fee_rate_for(db_session, "lazada") == 0.06
    assert await fee_rate_for(db_session, "tiktok_shop") == 0.08
    assert await fee_rate_for(db_session, "amazon") == 0.15
    assert await fee_rate_for(db_session, "shopify") == 0.0  # unknown -> no fee


@pytest.mark.asyncio
async def test_supplier_gate_denies_when_fee_kills_margin(db_session: AsyncSession):
    """Fee-aware gate: a high fee rate pushes margin below the 20% MIN rule."""
    await PolicyEngine.seed_default_rules(db_session)
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.FULL)
    product = await _product(db_session, price=5000)  # cost 3000 -> raw margin 40%
    order = await _order(db_session, product, platform="shopee", amount=5000)
    # shopee fee 0.07 -> margin (5000-3000-350)/5000 = 33% -> still allowed
    adapter = SupplierPODAdapter(client=object())
    so = await adapter.submit_order(db_session, order, product)
    assert so is not None
    # fee_rate 0.6 -> (5000-3000-3000)/5000 = -20% -> denied
    db_session.add(ChannelConnection(channel=ChannelType.SHOPEE, name="shopee-store",
                                     config={"fee_rate": 0.6}))
    await db_session.commit()
    order2 = await _order(db_session, product, platform="shopee", amount=5001)
    so2 = await adapter.submit_order(db_session, order2, product)
    assert so2 is None


# ── FX refresh ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fx_refresh_stores_rates(db_session: AsyncSession):
    def handler(request):
        assert str(request.url).startswith(LATEST_URL)
        return Response(200, json={"result": "success", "rates": {"MYR": 0.12, "VND": 7750.0}})

    transport = MockTransport(handler)
    async with AsyncClient(transport=transport) as client:
        count = await fx_refresh(db_session, http_client=client)
    assert count == 2
    conn = await db_session.scalar(
        select(ChannelConnection).where(ChannelConnection.channel == ChannelType.FX))
    assert conn is not None
    rates = conn.config["fx_rates"]["THB"]
    assert rates["MYR"] == 0.12 and rates["VND"] == 7750.0


# ── price sync: 24h lock + FX-aware caps ─────────────────────────────────────

@pytest.mark.asyncio
async def test_price_sync_respects_24h_lock(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    product = await _product(db_session)
    from datetime import datetime, timedelta
    product.created_at = datetime.utcnow() - timedelta(days=30)  # stale -> -10% signal
    db_session.add(PriceChangeLock(product_id=product.id, last_delta_percent=0.0))
    await db_session.commit()  # lock created NOW -> within 24h window
    result = await price_sync(db_session)
    assert result["applied"] == 0  # rate-limited by fresh lock
    assert result["skipped"] == 1
    await db_session.refresh(product)
    assert product.price_cents == 9900  # untouched


@pytest.mark.asyncio
async def test_price_sync_applies_with_stale_lock(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    product = await _product(db_session)
    from datetime import datetime, timedelta
    stale = PriceChangeLock(product_id=product.id, last_delta_percent=0.0)
    stale.last_change_at = datetime.utcnow() - timedelta(hours=48)
    db_session.add(stale)
    await db_session.commit()
    # fresh product -> stale signal: propose() returns None for new products!
    # Force a signal by aging the product too.
    product.created_at = datetime.utcnow() - timedelta(days=30)
    await db_session.commit()
    result = await price_sync(db_session)
    assert result["applied"] == 1  # stale lock no longer rate-limits
    await db_session.refresh(product)
    assert product.price_cents == 8910  # -10% stale signal


@pytest.mark.asyncio
async def test_price_sync_passes_fx_rate_for_foreign_currency(db_session: AsyncSession):
    # MYR product with fx_rates stored -> PRICE_CHANGE ABSOLUTE cap converts.
    await PolicyEngine.seed_default_rules(db_session)
    product = await _product(db_session, currency="MYR", price=10000)
    db_session.add(ChannelConnection(channel=ChannelType.FX, name="fx-rates",
                                     config={"fx_rates": {"THB": {"MYR": 0.12}}}))
    from datetime import datetime, timedelta
    product.created_at = datetime.utcnow() - timedelta(days=30)  # stale -> -10% signal
    await db_session.commit()
    result = await price_sync(db_session)
    assert result["applied"] == 1  # cap conversion did not block the change
    await db_session.refresh(product)
    assert product.price_cents == 9000

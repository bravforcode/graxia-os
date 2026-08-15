import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..channels.base import ChannelAdapter, ChannelError
from ..enums import ChannelType, SupplierStatus
from ..models import ChannelConnection, SupplierOrder, AdCampaignSync, PriceChangeLock


@pytest.mark.asyncio
async def test_channel_connection_crud(db_session: AsyncSession):
    conn = ChannelConnection(channel=ChannelType.SHOPIFY, name="main-store")
    db_session.add(conn)
    await db_session.commit()
    got = await db_session.scalar(select(ChannelConnection).where(ChannelConnection.channel == ChannelType.SHOPIFY))
    assert got is not None and got.enabled is True


@pytest.mark.asyncio
async def test_supplier_order_idempotency_key_unique(db_session: AsyncSession, sample_product_data, sample_customer_data):
    from ..models import Product, ProductStatus
    from ..services.order_service import OrderService
    product = Product(name=sample_product_data["name"], slug=sample_product_data["slug"],
                      price_cents=sample_product_data["price_cents"], status=ProductStatus.PUBLISHED)
    db_session.add(product)
    await db_session.commit()
    order = await OrderService.create_order(
        db_session, platform="shopify", platform_order_id="pod_uniq_1",
        customer_email=sample_customer_data["email"], product_id=product.id, amount_cents=9900,
    )
    so = SupplierOrder(order_id=order.id, supplier="printful", idempotency_key="ord-123")
    db_session.add(so)
    await db_session.commit()
    so2 = SupplierOrder(order_id=order.id, supplier="printful",
                        idempotency_key="ord-123")  # duplicate key must violate unique
    db_session.add(so2)
    with pytest.raises(Exception):
        await db_session.commit()


@pytest.mark.asyncio
async def test_ad_campaign_sync_unique_per_platform(db_session: AsyncSession):
    a = AdCampaignSync(platform="meta", platform_campaign_id="act_1")
    db_session.add(a)
    await db_session.commit()
    b = AdCampaignSync(platform="meta", platform_campaign_id="act_1")
    db_session.add(b)
    with pytest.raises(Exception):
        await db_session.commit()


@pytest.mark.asyncio
async def test_price_change_lock_singleton_per_product(db_session: AsyncSession):
    lock = PriceChangeLock(product_id="00000000-0000-0000-0000-000000000001", last_delta_percent=10.0)
    db_session.add(lock)
    await db_session.commit()
    got = await db_session.get(PriceChangeLock, "00000000-0000-0000-0000-000000000001")
    assert got.last_delta_percent == 10.0

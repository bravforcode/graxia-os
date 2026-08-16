"""Listing sync tests — real sync_products per adapter (sandbox shape),
listing ids persisted on ChannelInventory, sync_listings wiring."""
import pytest
from httpx import AsyncClient, MockTransport, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..channels.amazon import AmazonAdapter
from ..channels.lazada import LazadaAdapter
from ..channels.marketplace_sync import sync_listings
from ..channels.shopee import ShopeeAdapter
from ..channels.tiktok_shop import TikTokShopAdapter
from ..enums import ChannelType, ProductStatus
from ..models import ChannelConnection, ChannelInventory, Product


async def _product(db_session: AsyncSession, name="Test Product", price=19990) -> Product:
    product = Product(name=name, slug=name.lower().replace(" ", "-"),
                      price_cents=price, status=ProductStatus.PUBLISHED)
    db_session.add(product)
    await db_session.commit()
    return product


def _set_shopee_env(monkeypatch):
    monkeypatch.setenv("SHOPEE_PARTNER_ID", "123")
    monkeypatch.setenv("SHOPEE_PARTNER_KEY", "testkey")
    monkeypatch.setenv("SHOPEE_SHOP_ID", "456")


def _set_lazada_env(monkeypatch):
    monkeypatch.setenv("LAZADA_APP_KEY", "appkey")
    monkeypatch.setenv("LAZADA_APP_SECRET", "secret")
    monkeypatch.setenv("LAZADA_SELLER_ID", "seller1")


def _set_tiktok_env(monkeypatch):
    monkeypatch.setenv("TIKTOK_SHOP_APP_KEY", "appkey")
    monkeypatch.setenv("TIKTOK_SHOP_APP_SECRET", "testsecret")
    monkeypatch.setenv("TIKTOK_SHOP_SHOP_ID", "1001")


def _set_amazon_env(monkeypatch):
    monkeypatch.setenv("AMAZON_LWA_CLIENT_ID", "cid")
    monkeypatch.setenv("AMAZON_LWA_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("AMAZON_SP_API_ROLE_ARN", "arn:aws:iam::123:role/SP-API")
    monkeypatch.setenv("AMAZON_SELLER_ID", "seller1")


# ── Shopee ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_shopee_sync_products_adds_and_persists_item_id(db_session: AsyncSession, monkeypatch):
    _set_shopee_env(monkeypatch)
    product = await _product(db_session)
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = request.content.decode()
        return Response(200, json={"response": {"item_id": 999888}})

    transport = MockTransport(handler)
    async with AsyncClient(transport=transport) as client:
        adapter = ShopeeAdapter(config={"mode": "sandbox"}, http_client=client)
        pushed = await adapter.sync_products(db_session, [product])
    assert pushed == 1
    assert seen["path"] == "/api/v2/product/add_item"
    assert '"item_name":"Test Product"' in seen["body"]
    assert '"stock":0' in seen["body"]
    inv = await db_session.get(ChannelInventory, (ChannelType.SHOPEE, product.id))
    assert inv is not None and inv.listing_id == "999888"


@pytest.mark.asyncio
async def test_shopee_sync_products_updates_when_listed(db_session: AsyncSession, monkeypatch):
    _set_shopee_env(monkeypatch)
    product = await _product(db_session)
    db_session.add(ChannelInventory(channel=ChannelType.SHOPEE, product_id=product.id,
                                    channel_stock=7, stock_buffer=2, listing_id="item1"))
    await db_session.commit()
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = request.content.decode()
        return Response(200, json={"response": {}})

    transport = MockTransport(handler)
    async with AsyncClient(transport=transport) as client:
        adapter = ShopeeAdapter(config={"mode": "sandbox"}, http_client=client)
        await adapter.sync_products(db_session, [product])
    assert seen["path"] == "/api/v2/product/update_item"
    assert '"item_id":"item1"' in seen["body"]
    assert '"stock":7' in seen["body"]


# ── Lazada ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lazada_sync_products_creates(db_session: AsyncSession, monkeypatch):
    _set_lazada_env(monkeypatch)
    product = await _product(db_session)
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = request.content.decode()
        return Response(200, json={"data": {"item_id": "laz-item-1"}})

    transport = MockTransport(handler)
    async with AsyncClient(transport=transport) as client:
        adapter = LazadaAdapter(config={"mode": "sandbox"}, http_client=client)
        pushed = await adapter.sync_products(db_session, [product])
    assert pushed == 1
    assert seen["path"] == "/product/create"
    assert '"name":"Test Product"' in seen["body"]
    inv = await db_session.get(ChannelInventory, (ChannelType.LAZADA, product.id))
    assert inv.listing_id == "laz-item-1"


# ── TikTok ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tiktok_sync_products_creates(db_session: AsyncSession, monkeypatch):
    _set_tiktok_env(monkeypatch)
    product = await _product(db_session)
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = request.content.decode()
        return Response(200, json={"data": {"product_id": "tt-prod-1"}})

    transport = MockTransport(handler)
    async with AsyncClient(transport=transport) as client:
        adapter = TikTokShopAdapter(config={"mode": "sandbox"}, http_client=client)
        pushed = await adapter.sync_products(db_session, [product])
    assert pushed == 1
    assert seen["path"] == "/api/product/create"
    assert '"currency_code":"THB"' in seen["body"]
    inv = await db_session.get(ChannelInventory, (ChannelType.TIKTOK_SHOP, product.id))
    assert inv.listing_id == "tt-prod-1"


# ── Amazon (SKU-mapped PATCH only) ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_amazon_sync_products_patches_skus_only(db_session: AsyncSession, monkeypatch):
    _set_amazon_env(monkeypatch)
    listed = await _product(db_session, name="Listed Product")
    unlisted = await _product(db_session, name="Unlisted Product")
    db_session.add(ChannelInventory(channel=ChannelType.AMAZON, product_id=listed.id,
                                    channel_stock=5, stock_buffer=1, listing_id="SKU-1"))
    await db_session.commit()
    seen = {}

    def handler(request):
        if str(request.url).startswith("https://api.amazon.com/auth/o2/token"):
            return Response(200, json={"access_token": "t", "expires_in": 3600})
        if str(request.url).startswith("https://sts.amazonaws.com/"):
            return Response(200, text="""<AssumeRoleResponse xmlns="https://sts.amazonaws.com/doc/2011-06-15/">
<AssumeRoleResult><Credentials><AccessKeyId>AK</AccessKeyId><SecretAccessKey>SK</SecretAccessKey>
<SessionToken>ST</SessionToken><Expiration>2099-01-01T00:00:00Z</Expiration></Credentials>
</AssumeRoleResult></AssumeRoleResponse>""")
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = request.content.decode()
        return Response(200, json={"skus": ["SKU-1"]})

    transport = MockTransport(handler)
    async with AsyncClient(transport=transport) as client:
        adapter = AmazonAdapter(config={"mode": "sandbox"}, http_client=client)
        pushed = await adapter.sync_products(db_session, [listed, unlisted])
    assert pushed == 1  # unlisted product skipped (no SKU mapping)
    assert seen["method"] == "PATCH"
    assert seen["path"] == "/listings/2021-08-01/items/seller1/SKU-1"
    assert '"productType":"GENERIC"' in seen["body"]


# ── sync_listings wiring ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sync_listings_per_channel(db_session: AsyncSession, monkeypatch):
    _set_shopee_env(monkeypatch)
    _set_lazada_env(monkeypatch)
    _set_tiktok_env(monkeypatch)
    _set_amazon_env(monkeypatch)
    product = await _product(db_session)
    db_session.add(ChannelConnection(channel=ChannelType.SHOPEE, name="shopee-store",
                                     config={"mode": "sandbox"}))
    db_session.add(ChannelInventory(channel=ChannelType.SHOPEE, product_id=product.id,
                                    channel_stock=10, stock_buffer=3))
    db_session.add(ChannelConnection(channel=ChannelType.LAZADA, name="lazada-store",
                                     config={"mode": "sandbox"}))
    db_session.add(ChannelInventory(channel=ChannelType.LAZADA, product_id=product.id,
                                    channel_stock=10, stock_buffer=3))
    await db_session.commit()

    def handler(request):
        host = request.url.host
        if "shopee" in host:
            return Response(200, json={"response": {"item_id": 111}})
        if "lazada" in host:
            return Response(200, json={"data": {"item_id": 222}})
        return Response(404)

    transport = MockTransport(handler)
    # amazon/tiktok not connected -> skipped
    async with AsyncClient(transport=transport) as client:
        results = await sync_listings(db_session, http_client=client)
    assert results["shopee"]["pushed"] == 1
    assert results["lazada"]["pushed"] == 1
    assert results["tiktok_shop"]["skipped"] is True
    assert results["amazon"]["skipped"] is True
    inv = await db_session.get(ChannelInventory, (ChannelType.SHOPEE, product.id))
    assert inv.listing_id is not None

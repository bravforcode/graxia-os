"""TikTok Shop adapter tests — sandbox fixtures, poll-first import, sandbox gate."""
import pytest
from httpx import AsyncClient, MockTransport, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..channels import tiktok_shop as tt_mod
from ..channels.platform_auth import TikTokSigner
from ..channels.tiktok_shop import TIKTOK_STATUS_MAP, TikTokShopAdapter, reconcile_tiktok, trigger_tiktok_poll
from ..enums import ChannelType, IncidentSeverity, OrderStatus, ProductStatus
from ..models import IncidentEvent, Order, Product

SAMPLE_SEARCH = {
    "data": {
        "orders": [
            {
                "id": "tt_1001",
                "order_status": "AWAITING_SHIPMENT",
                "buyer_username": "tt_buyer",
                "payment_info": {"total_amount": {"amount": "299.00", "currency": "THB"}},
                "line_items": [{"product_id": "p1", "seller_sku": "SKU-1"}],
            },
            {
                "id": "tt_1002",
                "order_status": "UNPAID",
                "buyer_username": "tt_buyer2",
                "payment_info": {"total_amount": {"amount": "50.00", "currency": "THB"}},
                "line_items": [{"product_id": "p2"}],
            },
        ],
        "next_page_token": "",
    }
}


def _set_env(monkeypatch, **extra):
    monkeypatch.setenv("TIKTOK_SHOP_APP_KEY", "appkey")
    monkeypatch.setenv("TIKTOK_SHOP_APP_SECRET", "testsecret")
    monkeypatch.setenv("TIKTOK_SHOP_SHOP_ID", "1001")
    for k, v in extra.items():
        monkeypatch.setenv(k, v)


async def _product(db_session: AsyncSession) -> Product:
    product = Product(name="Test Product", slug="test-product",
                      price_cents=9900, status=ProductStatus.PUBLISHED)
    db_session.add(product)
    await db_session.commit()
    return product


# ── known-vector signature (hand-computed literals, independent of impl) ─────

def test_tiktok_signer_known_vector_get():
    signer = TikTokSigner(app_key="appkey", app_secret="testsecret")
    params = {"app_key": "appkey", "shop_id": "shop1", "status": "READY_TO_SHIP",
              "timestamp": "1712345678", "version": "202309"}
    sig = signer.sign("GET", "/api/order/search", params)
    assert sig == "c4812e633f3edbf330c2038fa44369d2299599cc044975fff9329c4e84ef1ac9"


def test_tiktok_signer_known_vector_post_with_body():
    signer = TikTokSigner(app_key="appkey", app_secret="testsecret")
    params = {"app_key": "appkey", "shop_id": "shop1", "status": "READY_TO_SHIP",
              "timestamp": "1712345678", "version": "202309"}
    sig = signer.sign("POST", "/api/order/search", params, body='{"page_size":20}')
    assert sig == "b577c9f27243b9affee861b7e367408a17a22e08264d54cdb36fafe625833b69"


# ── order poll parse ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_import_orders_parses_poll_payload(monkeypatch):
    _set_env(monkeypatch)
    transport = MockTransport(lambda req: Response(200, json=SAMPLE_SEARCH))
    async with AsyncClient(transport=transport) as client:
        adapter = TikTokShopAdapter(config={"mode": "sandbox"}, http_client=client)
        orders = await adapter.import_orders()
    assert len(orders) == 2
    first = orders[0]
    assert first["platform_order_id"] == "tt_1001"
    assert first["amount_cents"] == 29900
    assert first["currency"] == "THB"
    assert first["status"] == "paid"  # AWAITING_SHIPMENT -> paid (helper fulfills)
    assert orders[1]["status"] == "unpaid"  # unmapped status passes through


@pytest.mark.asyncio
async def test_poll_request_signed_with_body(monkeypatch):
    _set_env(monkeypatch)
    seen = {}

    def handler(request):
        seen["params"] = dict(request.url.params)
        seen["body"] = request.content.decode()
        return Response(200, json={"data": {"orders": []}})

    transport = MockTransport(handler)
    async with AsyncClient(transport=transport) as client:
        adapter = TikTokShopAdapter(config={"mode": "sandbox"}, http_client=client)
        await adapter.import_orders()
    p = seen["params"]
    assert p["app_key"] == "appkey" and p["shop_id"] == "1001"
    assert p["version"] == "202309"
    # signature covers sorted params + POST body (compact json)
    signer = TikTokSigner(app_key="appkey", app_secret="testsecret")
    signed = {k: v for k, v in p.items() if k != "sign"}
    expected = signer.sign("POST", "/api/order/search", signed, body=seen["body"])
    assert p["sign"] == expected


# ── sandbox gate ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mode_fails_closed_in_production_without_config(monkeypatch):
    _set_env(monkeypatch, APP_ENV="production")
    adapter = TikTokShopAdapter(config={})
    with pytest.raises(RuntimeError):
        adapter._mode()


@pytest.mark.asyncio
async def test_verify_webhook_fails_closed():
    assert await TikTokShopAdapter(config={"mode": "sandbox"}).verify_webhook(None) is False


# ── status map ───────────────────────────────────────────────────────────────

def test_status_map_rows():
    assert TIKTOK_STATUS_MAP == {
        "CANCELLED": OrderStatus.CANCELLED,
        "SHIPPED": OrderStatus.FULFILLED,
        "FULFILLED": OrderStatus.FULFILLED,
    }


@pytest.mark.asyncio
async def test_reconcile_applies_map_and_never_downgrades(db_session: AsyncSession):
    product = await _product(db_session)
    orders = {}
    for key, status in (("t1", OrderStatus.PENDING), ("t2", OrderStatus.PENDING),
                        ("t3", OrderStatus.REFUNDED)):
        order = Order(platform=ChannelType.TIKTOK_SHOP.value, platform_order_id=key,
                      customer_email="c@example.com", product_id=product.id,
                      amount_cents=1000, status=status)
        db_session.add(order)
        orders[key] = order
    await db_session.commit()

    result = await reconcile_tiktok(db_session, {
        "t1": "SHIPPED",        # -> FULFILLED
        "t2": "CANCELLED",      # -> CANCELLED
        "t3": "SHIPPED",        # local REFUNDED wins -> skip
        "t4": "UNKNOWN",        # unmapped -> skip
    })
    assert result == {"updated": 2, "skipped": 2}
    await db_session.refresh(orders["t1"])
    await db_session.refresh(orders["t2"])
    await db_session.refresh(orders["t3"])
    assert orders["t1"].status == OrderStatus.FULFILLED
    assert orders["t2"].status == OrderStatus.CANCELLED
    assert orders["t3"].status == OrderStatus.REFUNDED  # untouched


# ── idempotent import via shared helper ──────────────────────────────────────

@pytest.mark.asyncio
async def test_import_idempotent_via_shared_helper(db_session: AsyncSession):
    product = await _product(db_session)
    from ..channels.base import import_channel_orders
    orders = [{
        "platform_order_id": "tt_1001",
        "customer_email": "b@example.com",
        "amount_cents": 29900,
        "currency": "THB",
        "product_id": str(product.id),
        "status": "paid",
        "metadata": {"order_id": "tt_1001"},
    }]
    imported = await import_channel_orders(db_session, ChannelType.TIKTOK_SHOP.value, orders)
    assert imported == 1
    again = await import_channel_orders(db_session, ChannelType.TIKTOK_SHOP.value, orders)
    assert again == 0
    rows = (await db_session.execute(
        select(Order).where(Order.platform == ChannelType.TIKTOK_SHOP.value))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_unmappable_order_raises_incident(db_session: AsyncSession):
    from ..channels.base import import_channel_orders
    imported = await import_channel_orders(db_session, ChannelType.TIKTOK_SHOP.value, [{
        "platform_order_id": "no_prod",
        "customer_email": "b@example.com",
        "amount_cents": 1000,
        "currency": "THB",
        "product_id": None,
        "status": "paid",
        "metadata": {},
    }])
    assert imported == 0
    incidents = (await db_session.execute(select(IncidentEvent))).scalars().all()
    assert len(incidents) == 1
    assert incidents[0].severity == IncidentSeverity.LOW


# ── webhook trigger -> poll only ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_webhook_trigger_polls_never_imports_payload(db_session: AsyncSession, monkeypatch):
    polled = [{"platform_order_id": "p1", "customer_email": "b@example.com",
               "amount_cents": 1000, "currency": "THB", "product_id": None,
               "status": "paid", "metadata": {}}]
    calls = {}

    class _FakeAdapter:
        async def import_orders(self, since=None):
            return polled

    async def _fake_import(db, platform, orders):
        calls["platform"] = platform
        calls["orders"] = orders
        return 0

    monkeypatch.setattr(tt_mod, "import_channel_orders", _fake_import)
    result = await trigger_tiktok_poll(db_session, _FakeAdapter())
    assert result["fetched"] == 1
    assert calls["platform"] == ChannelType.TIKTOK_SHOP.value
    assert calls["orders"] == polled  # poll result only — no payload path


# ── fulfillment push ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_push_fulfillment_posts_ship(monkeypatch):
    _set_env(monkeypatch)
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["json"] = request.content.decode()
        return Response(200, json={"data": True})

    transport = MockTransport(handler)
    async with AsyncClient(transport=transport) as client:
        adapter = TikTokShopAdapter(config={"mode": "sandbox"}, http_client=client)
        order = type("O", (), {"metadata_": {"order_id": "tt_1001"}})()
        await adapter.push_fulfillment(order, tracking="TRK-9")
    assert seen["path"] == "/api/fulfillment/ship"
    assert '"tracking_number":"TRK-9"' in seen["json"]


@pytest.mark.asyncio
async def test_push_fulfillment_requires_order_id(monkeypatch):
    _set_env(monkeypatch)
    adapter = TikTokShopAdapter(config={"mode": "sandbox"})
    order = type("O", (), {"metadata_": {}})()
    with pytest.raises(Exception):
        await adapter.push_fulfillment(order, tracking="TRK-9")

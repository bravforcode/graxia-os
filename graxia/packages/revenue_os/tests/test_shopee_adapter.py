"""Shopee adapter tests — sandbox fixtures, poll-first import, sandbox gate."""
import pytest
from httpx import AsyncClient, MockTransport, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..channels import shopee as shopee_mod
from ..channels.shopee import SHOPEE_STATUS_MAP, ShopeeAdapter, reconcile_shopee, trigger_shopee_poll
from ..enums import ChannelType, IncidentSeverity, OrderStatus, ProductStatus
from ..models import IncidentEvent, Order, Product

SAMPLE_POLL = {
    "response": {
        "more": False,
        "next_cursor": "",
        "order_list": [
            {
                "order_sn": "221118XXXXABC",
                "order_status": "READY_TO_SHIP",
                "buyer_username": "buyer_one",
                "total_amount": {"currency": "MYR", "amount": "199.90"},
                "item_list": [{"item_id": 123456, "model_id": 0, "item_name": "Test Shirt"}],
            },
            {
                "order_sn": "221118XXXXDEF",
                "order_status": "PROCESSING",
                "buyer_user_name": "buyer_two",
                "total_amount": {"currency": "MYR", "amount": "50.00"},
                "item_list": [{"item_id": 789012, "model_id": 0}],
            },
        ],
    }
}


def _set_env(monkeypatch, **extra):
    monkeypatch.setenv("SHOPEE_PARTNER_ID", "123")
    monkeypatch.setenv("SHOPEE_PARTNER_KEY", "testkey")
    monkeypatch.setenv("SHOPEE_SHOP_ID", "456")
    for k, v in extra.items():
        monkeypatch.setenv(k, v)


async def _product(db_session: AsyncSession) -> Product:
    product = Product(name="Test Product", slug="test-product",
                      price_cents=9900, status=ProductStatus.PUBLISHED)
    db_session.add(product)
    await db_session.commit()
    return product


# ── order poll parse ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_import_orders_parses_poll_payload(monkeypatch):
    _set_env(monkeypatch)
    transport = MockTransport(lambda req: Response(200, json=SAMPLE_POLL))
    async with AsyncClient(transport=transport) as client:
        adapter = ShopeeAdapter(config={"mode": "sandbox"}, http_client=client)
        orders = await adapter.import_orders()
    assert len(orders) == 2
    first = orders[0]
    assert first["platform_order_id"] == "221118XXXXABC"
    assert first["amount_cents"] == 19990
    assert first["currency"] == "MYR"
    assert first["status"] == "paid"  # READY_TO_SHIP -> paid (helper fulfills)
    assert first["customer_email"] == "buyer_one@shopee.local"
    assert orders[1]["status"] == "processing"  # unmapped status passes through


@pytest.mark.asyncio
async def test_poll_request_is_signed(monkeypatch):
    _set_env(monkeypatch)
    seen = {}

    def handler(request):
        seen["params"] = dict(request.url.params)
        return Response(200, json={"response": {"order_list": []}})

    transport = MockTransport(handler)
    async with AsyncClient(transport=transport) as client:
        adapter = ShopeeAdapter(config={"mode": "sandbox"}, http_client=client)
        await adapter.import_orders()
    p = seen["params"]
    assert p["sign"]  # signature lands on the wire (sha256 hex, 64 chars)
    assert len(p["sign"]) == 64
    assert p["partner_id"] == "123" and p["shop_id"] == "456" and p["version"] == "2"


# ── sandbox gate ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mode_fails_closed_in_production_without_config(monkeypatch):
    _set_env(monkeypatch, APP_ENV="production")
    adapter = ShopeeAdapter(config={})  # mode unset
    with pytest.raises(RuntimeError):
        adapter._mode()


@pytest.mark.asyncio
async def test_mode_rejects_unknown_value(monkeypatch):
    _set_env(monkeypatch)
    adapter = ShopeeAdapter(config={"mode": "prod"})
    with pytest.raises(Exception):
        adapter._mode()


@pytest.mark.asyncio
async def test_verify_webhook_fails_closed():
    # Shopee callback signatures are not reliably verifiable -> never trust.
    assert await ShopeeAdapter(config={"mode": "sandbox"}).verify_webhook(None) is False


# ── status map ───────────────────────────────────────────────────────────────

def test_status_map_rows():
    assert SHOPEE_STATUS_MAP == {
        "READY_TO_SHIP": OrderStatus.PAID,
        "COMPLETED": OrderStatus.FULFILLED,
        "CANCELLED": OrderStatus.CANCELLED,
        "IN_CANCEL": OrderStatus.CANCELLED,
        "RETURNED": OrderStatus.REFUNDED,
    }


@pytest.mark.asyncio
async def test_reconcile_applies_map_and_never_downgrades(db_session: AsyncSession):
    product = await _product(db_session)
    orders = {}
    for key, status in (("o1", OrderStatus.PENDING), ("o2", OrderStatus.PENDING),
                        ("o3", OrderStatus.REFUNDED)):
        order = Order(platform=ChannelType.SHOPEE.value, platform_order_id=key,
                      customer_email="c@example.com", product_id=product.id,
                      amount_cents=1000, status=status)
        db_session.add(order)
        orders[key] = order
    await db_session.commit()

    result = await reconcile_shopee(db_session, {
        "o1": "COMPLETED",     # -> FULFILLED
        "o2": "IN_CANCEL",     # -> CANCELLED
        "o3": "COMPLETED",     # local REFUNDED wins -> skip
        "o4": "UNKNOWN_STATUS",  # no mapping -> skip
        "missing": "COMPLETED",  # unknown order -> skip
    })
    assert result == {"updated": 2, "skipped": 3}
    await db_session.refresh(orders["o1"])
    await db_session.refresh(orders["o2"])
    await db_session.refresh(orders["o3"])
    assert orders["o1"].status == OrderStatus.FULFILLED
    assert orders["o2"].status == OrderStatus.CANCELLED
    assert orders["o3"].status == OrderStatus.REFUNDED  # untouched


# ── shared idempotent import helper ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_import_channel_orders_shared_helper_idempotent(db_session: AsyncSession):
    product = await _product(db_session)
    orders = [{
        "platform_order_id": "shopee_1",
        "customer_email": "buyer@example.com",
        "amount_cents": 19990,
        "currency": "MYR",
        "product_id": str(product.id),
        "status": "paid",
        "metadata": {"order_sn": "shopee_1"},
    }]
    from ..channels.base import import_channel_orders
    imported = await import_channel_orders(db_session, ChannelType.SHOPEE.value, orders)
    assert imported == 1
    again = await import_channel_orders(db_session, ChannelType.SHOPEE.value, orders)
    assert again == 0  # idempotent
    rows = (await db_session.execute(
        select(Order).where(Order.platform == ChannelType.SHOPEE.value))).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == OrderStatus.PAID  # paid -> fulfill path ran


@pytest.mark.asyncio
async def test_unmappable_order_raises_incident_not_imported(db_session: AsyncSession):
    from ..channels.base import import_channel_orders
    imported = await import_channel_orders(db_session, ChannelType.SHOPEE.value, [{
        "platform_order_id": "no_product",
        "customer_email": "buyer@example.com",
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
    polled = [{
        "platform_order_id": "polled_1",
        "customer_email": "b@example.com",
        "amount_cents": 1000,
        "currency": "THB",
        "product_id": None,
        "status": "paid",
        "metadata": {},
    }]
    calls = {}

    class _FakeAdapter:
        async def import_orders(self, since=None):
            return polled

    async def _fake_import(db, platform, orders):
        calls["platform"] = platform
        calls["orders"] = orders
        return 0

    monkeypatch.setattr(shopee_mod, "import_channel_orders", _fake_import)
    result = await trigger_shopee_poll(db_session, _FakeAdapter())
    assert result["fetched"] == 1
    # The ONLY data that reaches the import helper is the poll result
    # (polling is the source of truth; no webhook payload path exists).
    assert calls["platform"] == ChannelType.SHOPEE.value
    assert calls["orders"] == polled


# ── fulfillment push ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_push_fulfillment_posts_ship_order(monkeypatch):
    _set_env(monkeypatch)
    seen = {}

    def handler(request):
        seen["json"] = request.content.decode()
        return Response(200, json={"response": {"package_list": [{"order_sn": "s1"}]}})

    transport = MockTransport(handler)
    async with AsyncClient(transport=transport) as client:
        adapter = ShopeeAdapter(config={"mode": "sandbox"}, http_client=client)
        order = type("O", (), {"metadata_": {"order_sn": "s1"}})()
        await adapter.push_fulfillment(order, tracking="TRACK123")
    assert '"order_sn":"s1"' in seen["json"]
    assert '"package_number":"TRACK123"' in seen["json"]


@pytest.mark.asyncio
async def test_push_fulfillment_requires_order_sn(monkeypatch):
    _set_env(monkeypatch)
    adapter = ShopeeAdapter(config={"mode": "sandbox"})
    order = type("O", (), {"metadata_": {}})()
    with pytest.raises(Exception):
        await adapter.push_fulfillment(order, tracking="TRACK123")

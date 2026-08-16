"""Lazada adapter tests — sandbox fixtures, poll-first import, sandbox gate."""
import hmac
import hashlib

import pytest
from httpx import AsyncClient, MockTransport, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..channels import lazada as lazada_mod
from ..channels.lazada import LAZADA_STATUS_MAP, LazadaAdapter, reconcile_lazada, trigger_lazada_poll
from ..channels.platform_auth import LazadaSigner
from ..enums import ChannelType, IncidentSeverity, OrderStatus, ProductStatus
from ..models import IncidentEvent, Order, Product

SAMPLE_ORDERS = {
    "data": [
        {
            "order_id": 9001,
            "order_number": "LZ-9001",
            "customer_email": "buyer@example.com",
            "statuses": ["shipped"],
            "price": "199.90",
            "currency": "MYR",
            "items": [{"order_item_id": 7001, "sku": "SKU-1"}],
        },
        {
            "order_id": 9002,
            "order_number": "LZ-9002",
            "customer_email": "buyer2@example.com",
            "statuses": ["pending"],
            "price": "50.00",
            "currency": "THB",
            "items": [],
        },
    ]
}


def _set_env(monkeypatch, **extra):
    monkeypatch.setenv("LAZADA_APP_KEY", "appkey")
    monkeypatch.setenv("LAZADA_APP_SECRET", "secret")
    monkeypatch.setenv("LAZADA_SELLER_ID", "seller1")
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
    transport = MockTransport(lambda req: Response(200, json=SAMPLE_ORDERS))
    async with AsyncClient(transport=transport) as client:
        adapter = LazadaAdapter(config={"mode": "sandbox"}, http_client=client)
        orders = await adapter.import_orders()
    assert len(orders) == 2
    first = orders[0]
    assert first["platform_order_id"] == "9001"
    assert first["amount_cents"] == 19990
    assert first["currency"] == "MYR"
    assert first["status"] == "paid"  # shipped -> paid (helper fulfills)
    assert first["metadata"]["order_item_id"] == 7001
    assert orders[1]["status"] == "pending"  # unmapped status passes through


# ── signed request via shared client ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_poll_request_signed_with_user_id(monkeypatch):
    _set_env(monkeypatch)
    seen = {}

    def handler(request):
        seen["params"] = dict(request.url.params)
        return Response(200, json={"data": []})

    transport = MockTransport(handler)
    async with AsyncClient(transport=transport) as client:
        adapter = LazadaAdapter(config={"mode": "sandbox"}, http_client=client)
        await adapter.import_orders()
    p = seen["params"]
    assert p["user_id"] == "seller1"
    # signature covers ALL params including user_id (formula already proven by
    # the known vector in test_platform_auth; here we verify the wire set)
    signer = LazadaSigner(app_key="appkey", app_secret="secret")
    signed = {k: v for k, v in p.items() if k != "sign"}
    expected = signer.sign("GET", "/orders/get", signed)
    assert p["sign"] == expected


# ── sandbox gate ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mode_fails_closed_in_production_without_config(monkeypatch):
    _set_env(monkeypatch, APP_ENV="production")
    adapter = LazadaAdapter(config={})
    with pytest.raises(RuntimeError):
        adapter._mode()


@pytest.mark.asyncio
async def test_verify_webhook_fails_closed():
    assert await LazadaAdapter(config={"mode": "sandbox"}).verify_webhook(None) is False


# ── status map ───────────────────────────────────────────────────────────────

def test_status_map_rows():
    assert LAZADA_STATUS_MAP == {
        "shipped": OrderStatus.FULFILLED,
        "delivered": OrderStatus.FULFILLED,
        "canceled": OrderStatus.CANCELLED,
        "returned": OrderStatus.REFUNDED,
    }


@pytest.mark.asyncio
async def test_reconcile_applies_map_and_never_downgrades(db_session: AsyncSession):
    product = await _product(db_session)
    orders = {}
    for key, status in (("9001", OrderStatus.PENDING), ("9002", OrderStatus.PENDING),
                        ("9003", OrderStatus.CANCELLED)):
        order = Order(platform=ChannelType.LAZADA.value, platform_order_id=key,
                      customer_email="c@example.com", product_id=product.id,
                      amount_cents=1000, status=status)
        db_session.add(order)
        orders[key] = order
    await db_session.commit()

    result = await reconcile_lazada(db_session, {
        "9001": "shipped",      # -> FULFILLED
        "9002": "returned",     # -> REFUNDED
        "9003": "shipped",      # local CANCELLED wins -> skip
        "9004": "mystery",      # unmapped -> skip
    })
    assert result == {"updated": 2, "skipped": 2}
    await db_session.refresh(orders["9001"])
    await db_session.refresh(orders["9002"])
    await db_session.refresh(orders["9003"])
    assert orders["9001"].status == OrderStatus.FULFILLED
    assert orders["9002"].status == OrderStatus.REFUNDED
    assert orders["9003"].status == OrderStatus.CANCELLED  # untouched


# ── idempotent import via shared helper ──────────────────────────────────────

@pytest.mark.asyncio
async def test_import_idempotent_via_shared_helper(db_session: AsyncSession):
    product = await _product(db_session)
    from ..channels.base import import_channel_orders
    orders = [{
        "platform_order_id": "9001",
        "customer_email": "buyer@example.com",
        "amount_cents": 19990,
        "currency": "MYR",
        "product_id": str(product.id),
        "status": "paid",
        "metadata": {"order_id": 9001},
    }]
    imported = await import_channel_orders(db_session, ChannelType.LAZADA.value, orders)
    assert imported == 1
    again = await import_channel_orders(db_session, ChannelType.LAZADA.value, orders)
    assert again == 0
    rows = (await db_session.execute(
        select(Order).where(Order.platform == ChannelType.LAZADA.value))).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == OrderStatus.PAID


@pytest.mark.asyncio
async def test_unmappable_order_raises_incident(db_session: AsyncSession):
    from ..channels.base import import_channel_orders
    imported = await import_channel_orders(db_session, ChannelType.LAZADA.value, [{
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

    monkeypatch.setattr(lazada_mod, "import_channel_orders", _fake_import)
    result = await trigger_lazada_poll(db_session, _FakeAdapter())
    assert result["fetched"] == 1
    assert calls["platform"] == ChannelType.LAZADA.value
    assert calls["orders"] == polled  # poll result only — no payload path


# ── fulfillment push ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_push_fulfillment_packs_then_ships(monkeypatch):
    _set_env(monkeypatch)
    paths = []

    def handler(request):
        paths.append(request.url.path)
        return Response(200, json={"data": True})

    transport = MockTransport(handler)
    async with AsyncClient(transport=transport) as client:
        adapter = LazadaAdapter(config={"mode": "sandbox"}, http_client=client)
        order = type("O", (), {"metadata_": {"order_id": 9001, "order_item_id": 7001}})()
        await adapter.push_fulfillment(order, tracking="TRK-1")
    assert paths == ["/order/pack", "/order/ship"]


@pytest.mark.asyncio
async def test_push_fulfillment_requires_metadata(monkeypatch):
    _set_env(monkeypatch)
    adapter = LazadaAdapter(config={"mode": "sandbox"})
    order = type("O", (), {"metadata_": {"order_id": 9001}})()  # no order_item_id
    with pytest.raises(Exception):
        await adapter.push_fulfillment(order, tracking="TRK-1")

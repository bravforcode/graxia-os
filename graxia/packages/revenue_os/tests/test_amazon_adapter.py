"""Amazon SP-API adapter tests — token cache, throttle backoff, PII-safe."""
import pytest
from httpx import AsyncClient, MockTransport, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..channels import amazon as amazon_mod
from ..channels.amazon import AMAZON_STATUS_MAP, AmazonAdapter, reconcile_amazon, trigger_amazon_poll
from ..channels.platform_auth import AmazonSigV4Signer, AmazonTokenCache
from ..enums import ChannelType, IncidentSeverity, OrderStatus, ProductStatus
from ..models import IncidentEvent, Order, Product

LWA_URL = "https://api.amazon.com/auth/o2/token"
STS_URL = "https://sts.amazonaws.com/"

STS_XML = """<AssumeRoleResponse xmlns="https://sts.amazonaws.com/doc/2011-06-15/">
<AssumeRoleResult><Credentials>
<AccessKeyId>ASIAEXAMPLE</AccessKeyId>
<SecretAccessKey>SECRETEXAMPLE</SecretAccessKey>
<SessionToken>TOKENEXAMPLE</SessionToken>
<Expiration>2099-01-01T00:00:00Z</Expiration>
</Credentials></AssumeRoleResult></AssumeRoleResponse>"""

SAMPLE_ORDERS = {
    "payload": {
        "Orders": [
            {
                "AmazonOrderId": "amz_1",
                "OrderStatus": "Unshipped",
                "FulfillmentChannel": "MFN",
                "BuyerEmail": "buyer@example.com",
                "BuyerName": "Jane Buyer",
                "ShippingAddress": {"Name": "Jane Buyer", "AddressLine1": "1 Secret St"},
                "OrderTotal": {"Amount": "199.90", "CurrencyCode": "USD"},
                "OrderItems": [{"OrderItemId": "item_1"}],
            },
            {
                "AmazonOrderId": "amz_2",
                "OrderStatus": "Unshipped",
                "FulfillmentChannel": "AFN",  # FBA -> filtered out (MFN only)
                "BuyerEmail": "fba@example.com",
                "OrderTotal": {"Amount": "50.00", "CurrencyCode": "USD"},
                "OrderItems": [],
            },
        ]
    }
}


def _set_env(monkeypatch, **extra):
    monkeypatch.setenv("AMAZON_LWA_CLIENT_ID", "cid")
    monkeypatch.setenv("AMAZON_LWA_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("AMAZON_SP_API_ROLE_ARN", "arn:aws:iam::123:role/SP-API")
    monkeypatch.setenv("AMAZON_SELLER_ID", "seller1")
    for k, v in extra.items():
        monkeypatch.setenv(k, v)


def _transport_handler(orders_json=SAMPLE_ORDERS, calls=None):
    def handler(request):
        if calls is not None:
            calls.append(request.url.path)
        if str(request.url).startswith(LWA_URL):
            return Response(200, json={"access_token": "lwa_token", "expires_in": 3600})
        if str(request.url).startswith(STS_URL):
            return Response(200, text=STS_XML)
        if request.url.path.startswith("/orders/v0/orders"):
            return Response(200, json=orders_json)
        return Response(404)
    return handler


async def _product(db_session: AsyncSession) -> Product:
    product = Product(name="Test Product", slug="test-product",
                      price_cents=9900, status=ProductStatus.PUBLISHED)
    db_session.add(product)
    await db_session.commit()
    return product


# ── SigV4 known vector (pinned get-vanilla shape; verified vs botocore) ──────

def test_sigv4_known_vector():
    signer = AmazonSigV4Signer(access_key="AKIDEXAMPLE", secret_key="wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
                               region="us-east-1", service="service")
    authz = signer.sign("GET", "/", "", {"host": "example.amazonaws.com",
                                         "x-amz-date": "20130524T000000Z"}, "", "20130524T000000Z")
    assert authz == ("AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20130524/us-east-1/service/aws4_request, "
                     "SignedHeaders=host;x-amz-date, "
                     "Signature=6b52c88578c3a6e09e219aaa1b56c53f15bc2ad1a7d2bc31287ecaf19c2d2174")


# ── token cache ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_token_cache_caches_and_refreshes():
    hits = {"n": 0}

    def handler(request):
        hits["n"] += 1
        return Response(200, json={"access_token": f"tok{hits['n']}", "expires_in": 3600})

    transport = MockTransport(handler)
    async with AsyncClient(transport=transport) as client:
        cache = AmazonTokenCache("cid", "csecret", http_client=client)
        t1 = await cache.get_token()
        t2 = await cache.get_token()
        assert t1 == t2 == "tok1" and hits["n"] == 1  # cached within window
        t3 = await cache.force_refresh()
        assert t3 == "tok2" and hits["n"] == 2  # forced refresh hits LWA again


@pytest.mark.asyncio
async def test_assume_role_parses_creds_and_caches():
    hits = {"n": 0}

    def handler(request):
        if str(request.url).startswith(LWA_URL):
            return Response(200, json={"access_token": "lwa_token", "expires_in": 3600})
        hits["n"] += 1
        return Response(200, text=STS_XML)

    transport = MockTransport(handler)
    async with AsyncClient(transport=transport) as client:
        cache = AmazonTokenCache("cid", "csecret", http_client=client)
        creds = await cache.assume_role("arn:aws:iam::123:role/SP-API")
        assert creds["access_key"] == "ASIAEXAMPLE"
        assert creds["secret_key"] == "SECRETEXAMPLE"
        assert creds["session_token"] == "TOKENEXAMPLE"
        again = await cache.assume_role("arn:aws:iam::123:role/SP-API")
        assert again is creds and hits["n"] == 1  # cached until expiry


# ── throttle backoff ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_throttle_backoff_honors_rate_limit_header(monkeypatch):
    _set_env(monkeypatch)
    calls = {"n": 0}
    sleeps = []
    real_sleep = __import__("asyncio").sleep

    async def fake_sleep(secs):
        sleeps.append(secs)
        await real_sleep(0)  # don't actually wait

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    def handler(request):
        if str(request.url).startswith((LWA_URL, STS_URL)):
            if str(request.url).startswith(LWA_URL):
                return Response(200, json={"access_token": "t", "expires_in": 3600})
            return Response(200, text=STS_XML)
        calls["n"] += 1
        if calls["n"] < 3:  # 2 throttled order calls then success
            return Response(429, headers={"x-amzn-RateLimit-Limit": "2.0"})  # -> 0.5s wait
        return Response(200, json={"payload": {"Orders": []}})

    transport = MockTransport(handler)
    async with AsyncClient(transport=transport) as client:
        adapter = AmazonAdapter(config={"mode": "sandbox"}, http_client=client)
        await adapter.import_orders()
    assert calls["n"] == 3  # 2 throttled order calls + success
    assert len(sleeps) >= 2
    assert 0.4 <= sleeps[0] <= 0.6  # 1/2.0 = 0.5s base honored
    assert 0.9 <= sleeps[1] <= 1.1  # attempt multiplier applies


# ── order poll parse + PII ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_import_orders_parses_payload_pii_redacted(monkeypatch):
    _set_env(monkeypatch)
    logged = []

    class _Recorder:
        def info(self, *a, **kw):
            logged.append((a, kw))

    monkeypatch.setattr(amazon_mod, "logger", _Recorder())
    transport = MockTransport(_transport_handler())
    async with AsyncClient(transport=transport) as client:
        adapter = AmazonAdapter(config={"mode": "sandbox"}, http_client=client)
        orders = await adapter.import_orders()
    assert len(orders) == 1  # FBA order filtered out (MFN only)
    first = orders[0]
    assert first["platform_order_id"] == "amz_1"
    assert first["amount_cents"] == 19990
    assert first["currency"] == "USD"
    assert first["status"] == "paid"  # Unshipped -> paid
    # structural PII redaction: metadata has ids only
    assert set(first["metadata"]) == {"amazon_order_id", "order_item_ids"}
    assert first["metadata"]["amazon_order_id"] == "amz_1"
    # log capture: no PII values anywhere in logged events
    blob = repr(logged)
    assert "buyer@example.com" not in blob
    assert "Jane Buyer" not in blob
    assert "1 Secret St" not in blob
    assert "amz_1" in blob  # order ids are fine to log


# ── status map ───────────────────────────────────────────────────────────────

def test_status_map_rows():
    assert AMAZON_STATUS_MAP == {
        "CancelPending": OrderStatus.CANCELLED,
        "Canceled": OrderStatus.CANCELLED,
        "Shipped": OrderStatus.FULFILLED,
        "Pending": OrderStatus.PENDING,
    }


@pytest.mark.asyncio
async def test_reconcile_applies_map_and_never_downgrades(db_session: AsyncSession):
    product = await _product(db_session)
    orders = {}
    for key, status in (("a1", OrderStatus.PENDING), ("a2", OrderStatus.PENDING),
                        ("a3", OrderStatus.CANCELLED)):
        order = Order(platform=ChannelType.AMAZON.value, platform_order_id=key,
                      customer_email="c@example.com", product_id=product.id,
                      amount_cents=1000, status=status)
        db_session.add(order)
        orders[key] = order
    await db_session.commit()

    result = await reconcile_amazon(db_session, {
        "a1": "Shipped",        # -> FULFILLED
        "a2": "Canceled",       # -> CANCELLED
        "a3": "Shipped",        # local CANCELLED wins -> skip
        "a4": "Mystery",        # unmapped -> skip
    })
    assert result == {"updated": 2, "skipped": 2}
    await db_session.refresh(orders["a1"])
    await db_session.refresh(orders["a2"])
    await db_session.refresh(orders["a3"])
    assert orders["a1"].status == OrderStatus.FULFILLED
    assert orders["a2"].status == OrderStatus.CANCELLED
    assert orders["a3"].status == OrderStatus.CANCELLED  # untouched


# ── idempotent import via shared helper ──────────────────────────────────────

@pytest.mark.asyncio
async def test_import_idempotent_via_shared_helper(db_session: AsyncSession):
    product = await _product(db_session)
    from ..channels.base import import_channel_orders
    orders = [{
        "platform_order_id": "amz_1",
        "customer_email": "b@example.com",
        "amount_cents": 19990,
        "currency": "USD",
        "product_id": str(product.id),
        "status": "paid",
        "metadata": {"amazon_order_id": "amz_1"},
    }]
    imported = await import_channel_orders(db_session, ChannelType.AMAZON.value, orders)
    assert imported == 1
    again = await import_channel_orders(db_session, ChannelType.AMAZON.value, orders)
    assert again == 0
    rows = (await db_session.execute(
        select(Order).where(Order.platform == ChannelType.AMAZON.value))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_unmappable_order_raises_incident(db_session: AsyncSession):
    from ..channels.base import import_channel_orders
    imported = await import_channel_orders(db_session, ChannelType.AMAZON.value, [{
        "platform_order_id": "no_prod",
        "customer_email": "b@example.com",
        "amount_cents": 1000,
        "currency": "USD",
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
               "amount_cents": 1000, "currency": "USD", "product_id": None,
               "status": "paid", "metadata": {}}]
    calls = {}

    class _FakeAdapter:
        async def import_orders(self, since=None):
            return polled

    async def _fake_import(db, platform, orders):
        calls["platform"] = platform
        calls["orders"] = orders
        return 0

    monkeypatch.setattr(amazon_mod, "import_channel_orders", _fake_import)
    result = await trigger_amazon_poll(db_session, _FakeAdapter())
    assert result["fetched"] == 1
    assert calls["platform"] == ChannelType.AMAZON.value
    assert calls["orders"] == polled  # poll result only — no payload path


# ── sandbox gate + fulfillment ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mode_fails_closed_in_production_without_config(monkeypatch):
    _set_env(monkeypatch, APP_ENV="production")
    adapter = AmazonAdapter(config={})
    with pytest.raises(RuntimeError):
        adapter._mode()


@pytest.mark.asyncio
async def test_push_fulfillment_posts_shipment(monkeypatch):
    _set_env(monkeypatch)
    seen = {}

    def handler(request):
        if str(request.url).startswith(LWA_URL):
            return Response(200, json={"access_token": "t", "expires_in": 3600})
        if str(request.url).startswith(STS_URL):
            return Response(200, text=STS_XML)
        seen["path"] = request.url.path
        seen["body"] = request.content.decode()
        return Response(200, json={"payload": {"Order": {}}})

    transport = MockTransport(handler)
    async with AsyncClient(transport=transport) as client:
        adapter = AmazonAdapter(config={"mode": "sandbox"}, http_client=client)
        order = type("O", (), {"metadata_": {"amazon_order_id": "amz_1",
                                             "order_item_ids": ["item_1"]}})()
        await adapter.push_fulfillment(order, tracking="TRK-77")
    assert seen["path"] == "/orders/v0/orders/amz_1/shipment"
    assert '"TrackingNumber":"TRK-77"' in seen["body"]


@pytest.mark.asyncio
async def test_push_fulfillment_requires_order_id(monkeypatch):
    _set_env(monkeypatch)
    adapter = AmazonAdapter(config={"mode": "sandbox"})
    order = type("O", (), {"metadata_": {}})()
    with pytest.raises(Exception):
        await adapter.push_fulfillment(order, tracking="TRK-77")

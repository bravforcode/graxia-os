import hashlib
import hmac
import pytest
from httpx import AsyncClient, MockTransport, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..channels.shopify import ShopifyAdapter, ShopifyClient, import_shopify_orders, reconcile_shopify
from ..enums import OrderStatus, ProductStatus
from ..models import Order, Product


def _hmac(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class _FakeRequest:
    def __init__(self, body: bytes, sig: str):
        self._body = body
        self._headers = {"x-shopify-hmac-sha256": sig}

    async def body(self):
        return self._body

    @property
    def headers(self):
        return self._headers


@pytest.mark.asyncio
async def test_verify_webhook_ok(monkeypatch):
    monkeypatch.setenv("SHOPIFY_WEBHOOK_SECRET", "sec")
    payload = b'{"id": 1}'
    req = _FakeRequest(payload, _hmac(payload, "sec"))
    assert await ShopifyAdapter().verify_webhook(req) is True


@pytest.mark.asyncio
async def test_verify_webhook_bad(monkeypatch):
    monkeypatch.setenv("SHOPIFY_WEBHOOK_SECRET", "sec")
    req = _FakeRequest(b'{"id": 1}', "deadbeef")
    assert await ShopifyAdapter().verify_webhook(req) is False


@pytest.mark.asyncio
async def test_client_retries_on_429(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return Response(429, headers={"Retry-After": "0"})
        return Response(200, json={"orders": []})

    transport = MockTransport(handler)
    async with AsyncClient(transport=transport) as client:
        shopify = ShopifyClient(domain="test.myshopify.com", token="t", http_client=client)
        data = await shopify.get_json("/admin/api/2024-01/orders.json")
    assert calls["n"] == 2
    assert data == {"orders": []}


@pytest.mark.asyncio
async def test_import_shopify_orders_idempotent(db_session: AsyncSession, sample_product_data):
    product = Product(name=sample_product_data["name"], slug=sample_product_data["slug"],
                      price_cents=sample_product_data["price_cents"], status=ProductStatus.PUBLISHED)
    db_session.add(product)
    await db_session.commit()
    orders = [{
        "platform_order_id": "shop_1",
        "customer_email": "buyer@example.com",
        "amount_cents": 9900,
        "currency": "THB",
        "product_id": str(product.id),
        "status": "paid",
        "metadata": {"shopify_id": 1001},
    }]
    imported = await import_shopify_orders(db_session, orders)
    assert imported == 1
    again = await import_shopify_orders(db_session, orders)
    assert again == 0  # idempotent
    rows = (await db_session.execute(select(Order).where(Order.platform == "shopify"))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_reconcile_does_not_downgrade_local_refunded(db_session: AsyncSession, sample_product_data, sample_customer_data):
    product = Product(name=sample_product_data["name"], slug=sample_product_data["slug"],
                      price_cents=sample_product_data["price_cents"], status=ProductStatus.PUBLISHED)
    db_session.add(product)
    await db_session.commit()
    from ..services.order_service import OrderService
    order = await OrderService.create_order(
        db_session, platform="shopify", platform_order_id="shop_ref_1",
        customer_email=sample_customer_data["email"], product_id=product.id, amount_cents=9900,
    )
    order.status = OrderStatus.REFUNDED  # local truth
    await db_session.commit()
    # external says 'paid' — must NOT downgrade
    external = {"shop_ref_1": "paid"}
    result = await reconcile_shopify(db_session, external)
    assert result["updated"] == 0
    await db_session.refresh(order)
    assert order.status == OrderStatus.REFUNDED

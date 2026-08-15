"""Regression test: ShopifyAdapter.import_orders must not NameError (Decimal import)."""
import pytest
from httpx import AsyncClient, MockTransport, Response

from ..channels.shopify import ShopifyAdapter


@pytest.mark.asyncio
async def test_import_orders_parses_decimal_amounts(monkeypatch):
    def handler(request):
        assert "/orders.json" in request.url.path
        return Response(200, json={"orders": [
            {"id": 2001, "total_price": "19.99", "currency": "USD", "name": "#1001",
             "financial_status": "paid", "customer": {"email": "buyer@example.com"},
             "line_items": [{"properties": [{"name": "graxia_product_id", "value": "p-1"}]}]},
        ]})

    monkeypatch.setenv("SHOPIFY_STORE_DOMAIN", "test.myshopify.com")
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "t")
    adapter = ShopifyAdapter()
    adapter._client = lambda: ShopifyClientForTest(handler)  # bypass env client
    orders = await adapter.import_orders()
    assert orders[0]["amount_cents"] == 1999  # Decimal rounding, not float truncation
    assert orders[0]["product_id"] == "p-1"
    assert orders[0]["status"] == "paid"


class ShopifyClientForTest:
    """Minimal stand-in exercising the adapter's Decimal path without HTTP."""
    def __init__(self, handler):
        self.handler = handler

    async def get_json(self, path: str, params=None):
        import httpx
        async with AsyncClient(transport=MockTransport(self.handler)) as client:
            resp = await client.get("https://x" + path, params=params or {})
            return resp.json()

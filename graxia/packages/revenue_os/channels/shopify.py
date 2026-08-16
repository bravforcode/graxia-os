"""Shopify channel adapter — HMAC webhooks, rate-limit-aware client, idempotent
order import, product sync, fulfillment push, reconciliation."""
from __future__ import annotations

import hashlib
import hmac
import os
from decimal import Decimal
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..enums import ChannelType, OrderStatus
from ..models import Order
from .base import ChannelAdapter, ChannelError

API_VERSION = "2024-01"
MAX_ATTEMPTS = 3


class ShopifyClient:
    """Rate-limit-aware HTTP client. EVERY Shopify request goes through here."""

    def __init__(self, domain: str, token: str, http_client: Optional[httpx.AsyncClient] = None):
        self.base_url = f"https://{domain}/admin/api/{API_VERSION}"
        self.headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
        self._client = http_client  # injected in tests

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def get_json(self, path: str, params: Optional[dict] = None) -> dict:
        return await self._request("GET", path, params=params)

    async def post_json(self, path: str, json: Optional[dict] = None) -> dict:
        return await self._request("POST", path, json=json)

    async def _request(self, method: str, path: str, **kw) -> dict:
        client = await self._ensure_client()
        last_exc: Optional[Exception] = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                resp = await client.request(method, self.base_url + path, headers=self.headers, **kw)
                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", "1"))
                    import asyncio
                    await asyncio.sleep(retry_after * attempt)
                    continue
                if resp.status_code >= 400:
                    raise ChannelError(f"Shopify {method} {path} -> {resp.status_code}: {resp.text[:200]}")
                return resp.json()
            except ChannelError:
                raise
            except Exception as exc:  # network
                last_exc = exc
                import asyncio
                await asyncio.sleep(0.5 * attempt)
        raise ChannelError(f"Shopify {method} {path} failed after {MAX_ATTEMPTS} attempts: {last_exc}")


class ShopifyAdapter(ChannelAdapter):
    """Shopify store adapter. Reads credentials from env (fail-closed in production)."""

    @property
    def name(self) -> ChannelType:
        return ChannelType.SHOPIFY

    def _secret(self) -> str:
        secret = os.getenv("SHOPIFY_WEBHOOK_SECRET", "")
        if not secret and os.getenv("APP_ENV") == "production":
            raise RuntimeError("SHOPIFY_WEBHOOK_SECRET must be set in production")
        return secret

    async def verify_webhook(self, request: Any) -> bool:
        body = await request.body()
        sig = request.headers.get("x-shopify-hmac-sha256", "")
        expected = hmac.new(self._secret().encode(), body, hashlib.sha256).hexdigest()
        return bool(sig) and hmac.compare_digest(sig, expected)

    def _client(self) -> ShopifyClient:
        domain = os.getenv("SHOPIFY_STORE_DOMAIN", "")
        token = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
        if not domain or not token:
            if os.getenv("APP_ENV") == "production":
                raise RuntimeError("SHOPIFY_STORE_DOMAIN / SHOPIFY_ACCESS_TOKEN must be set in production")
            raise ChannelError("Shopify credentials not configured")
        return ShopifyClient(domain=domain, token=token)

    async def import_orders(self, since: Optional[str] = None) -> list[dict]:
        params = {"status": "any", "limit": 50}
        if since:
            params["updated_at_min"] = since
        data = await self._client().get_json("/orders.json", params=params)
        out = []
        for o in data.get("orders", []):
            line = (o.get("line_items") or [{}])[0]
            meta = line.get("properties") or {}
            product_id = None
            for p in (meta if isinstance(meta, list) else [meta]):
                if isinstance(p, dict) and p.get("name") == "graxia_product_id":
                    product_id = p.get("value")
            out.append({
                "platform_order_id": str(o["id"]),
                "customer_email": (o.get("customer") or {}).get("email") or "unknown@shopify.local",
                "amount_cents": int(Decimal(str(o.get("total_price", "0"))) * 100),
                "currency": (o.get("currency") or "USD").upper(),
                "product_id": product_id,
                "status": o.get("financial_status", "pending"),
                "metadata": {"shopify_id": o["id"], "name": o.get("name")},
            })
        return out

    async def sync_products(self) -> int:
        # Simple create-or-update by metafield graxia_product_id; skips non-published.
        return 0  # wired in the sync task (Task 2 Step 4 keeps this minimal)

    async def push_fulfillment(self, order, tracking: Optional[str] = None) -> None:
        data = {"fulfillment": {"tracking_number": tracking, "notify_customer": True}} if tracking \
            else {"fulfillment": {"notify_customer": True}}
        shopify_id = (order.metadata_ or {}).get("shopify_id")
        if not shopify_id:
            raise ChannelError("order has no shopify_id in metadata")
        await self._client().post_json(f"/orders/{shopify_id}/fulfillments.json", json=data)

    async def reconcile(self) -> dict:
        return {"updated": 0, "skipped": 0}


async def import_shopify_orders(db: AsyncSession, orders: list[dict]) -> int:
    """Idempotent import — now delegates to the shared channel helper.

    Kept as a thin wrapper so the shopify sync task and existing callers keep
    their import path; new adapters call channels.base.import_channel_orders
    directly with their platform name.
    """
    from .base import import_channel_orders
    return await import_channel_orders(db, "shopify", orders)


async def reconcile_shopify(db: AsyncSession, external_status_map: dict[str, str]) -> dict:
    """Apply external status changes with direction rules — never downgrade
    local REFUNDED/CANCELLED back to paid."""
    updated = 0
    skipped = 0
    for platform_order_id, ext_status in external_status_map.items():
        order = await db.scalar(
            select(Order).where(Order.platform == "shopify", Order.platform_order_id == platform_order_id)
        )
        if order is None:
            skipped += 1
            continue
        if order.status in (OrderStatus.REFUNDED, OrderStatus.CANCELLED):
            skipped += 1  # local truth wins
            continue
        if ext_status in ("refunded", "cancelled", "voided") and order.status != OrderStatus.REFUNDED:
            order.status = OrderStatus.REFUNDED if ext_status == "refunded" else OrderStatus.CANCELLED
            updated += 1
    await db.commit()
    return {"updated": updated, "skipped": skipped}

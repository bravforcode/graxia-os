"""Shopee Open Platform adapter — poll-first order import, sandbox gate.

POLLING IS THE SOURCE OF TRUTH (risk audit #1): Shopee callback signature
formats vary and are not reliably verifiable, so `verify_webhook` fails closed
and webhooks only ever trigger `trigger_shopee_poll` — the webhook payload is
never imported directly. All outbound calls go through ShopeeClient (the only
place signing lives). Mode comes from ChannelConnection.config["mode"] and is
fail-closed in production when unset (risk audit #8).
"""
from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..enums import ChannelType, OrderStatus
from ..models import Order
from .base import ChannelAdapter, ChannelError, import_channel_orders
from .platform_auth import ShopeeClient

# Shopee order_status -> local OrderStatus (per-platform map, tested).
# READY_TO_SHIP means payment captured, awaiting shipment -> PAID locally.
SHOPEE_STATUS_MAP = {
    "READY_TO_SHIP": OrderStatus.PAID,
    "COMPLETED": OrderStatus.FULFILLED,
    "CANCELLED": OrderStatus.CANCELLED,
    "IN_CANCEL": OrderStatus.CANCELLED,
    "RETURNED": OrderStatus.REFUNDED,
}

# Import normalization: READY_TO_SHIP arrives as "paid" so the shared helper
# fulfills it; everything else is passed through lowercased (PENDING).
_IMPORT_STATUS_MAP = {"READY_TO_SHIP": "paid"}

REQUIRED_ENV = ("SHOPEE_PARTNER_ID", "SHOPEE_PARTNER_KEY", "SHOPEE_SHOP_ID")


class ShopeeAdapter(ChannelAdapter):
    """Shopee store adapter. Credentials from env; mode from channel config."""

    def __init__(self, config: Optional[dict] = None, http_client: Optional[Any] = None):
        self.config = config or {}
        self._http_client = http_client

    @property
    def name(self) -> ChannelType:
        return ChannelType.SHOPEE

    # ── sandbox gate ───────────────────────────────────────────────────
    def _mode(self) -> str:
        mode = self.config.get("mode")
        if mode:
            if mode not in ("sandbox", "live"):
                raise ChannelError(f"Shopee mode must be sandbox|live, got {mode!r}")
            return mode
        if os.getenv("APP_ENV") == "production":
            raise RuntimeError("Shopee channel mode unset in production — refuse to run")
        return "sandbox"

    def _credentials(self) -> dict:
        missing = [v for v in REQUIRED_ENV if not os.getenv(v)]
        if missing:
            if os.getenv("APP_ENV") == "production":
                raise RuntimeError(f"Shopee credentials missing in production: {missing}")
            raise ChannelError(f"Shopee credentials not configured: {missing}")
        return {
            "partner_id": int(os.getenv("SHOPEE_PARTNER_ID")),
            "partner_key": os.getenv("SHOPEE_PARTNER_KEY"),
            "shop_id": int(os.getenv("SHOPEE_SHOP_ID")),
        }

    def _client(self) -> ShopeeClient:
        creds = self._credentials()
        return ShopeeClient(
            partner_id=creds["partner_id"],
            partner_key=creds["partner_key"],
            shop_id=creds["shop_id"],
            mode=self._mode(),
            access_token=os.getenv("SHOPEE_ACCESS_TOKEN", ""),
            http_client=self._http_client,
        )

    # ── webhook (fail-closed; poll is the source of truth) ─────────────
    async def verify_webhook(self, request: Any) -> bool:
        # Shopee callback signatures vary by region/endpoint and are not
        # reliably HMAC-verifiable (risk audit #1). Refuse to trust any
        # callback; polling is the only import path.
        return False

    async def import_orders(self, since: Optional[str] = None) -> list[dict]:
        params: dict = {"status": "READY_TO_SHIP", "page_size": 50,
                        "time_range_field": "update_time"}
        if since:
            try:
                params["time_from"] = int(datetime.fromisoformat(since).timestamp())
            except ValueError:
                params["time_from"] = 0
        data = await self._client().get_json("/order/get_order_list", params=params)
        out = []
        for o in (data.get("response") or {}).get("order_list", []):
            total = o.get("total_amount") or {}
            amount = Decimal(str(total.get("amount", "0")))
            buyer = o.get("buyer_username") or o.get("buyer_user_name") or "unknown"
            item = (o.get("item_list") or [{}])[0]
            out.append({
                "platform_order_id": str(o.get("order_sn", "")),
                "customer_email": f"{buyer}@shopee.local",
                "amount_cents": int(amount * 100),
                "currency": (total.get("currency") or "THB").upper(),
                "product_id": None,  # item_id mapping arrives with inventory sync (Task 6)
                "status": _IMPORT_STATUS_MAP.get(o.get("order_status", ""), o.get("order_status", "").lower()),
                "metadata": {"order_sn": o.get("order_sn"), "item_id": item.get("item_id"),
                             "order_status": o.get("order_status")},
            })
        return out

    async def sync_products(self, db: AsyncSession, products: Optional[list] = None) -> int:
        """Push products to Shopee (add_item / update_item by stored item_id).
        Persists the returned item_id on the ChannelInventory row."""
        from ..models import ChannelInventory
        pushed = 0
        for product in (products or []):
            inv = await db.get(ChannelInventory, (ChannelType.SHOPEE, product.id))
            stock = inv.channel_stock if inv is not None else 0
            payload = {
                "item_name": product.name,
                "original_price": f"{Decimal(product.price_cents or 0) / 100:.2f}",
                "stock": stock,
            }
            if inv is not None and inv.listing_id:
                payload["item_id"] = inv.listing_id
                await self._client().post_json("/product/update_item", json=payload)
            else:
                data = await self._client().post_json("/product/add_item", json=payload)
                item_id = (data.get("response") or {}).get("item_id")
                if inv is None:
                    inv = ChannelInventory(channel=ChannelType.SHOPEE, product_id=product.id,
                                           channel_stock=0, stock_buffer=0,
                                           listing_id=str(item_id) if item_id else None)
                    db.add(inv)
                elif item_id:
                    inv.listing_id = str(item_id)
            pushed += 1
        await db.commit()
        return pushed

    async def push_fulfillment(self, order, tracking: Optional[str] = None) -> None:
        order_sn = (order.metadata_ or {}).get("order_sn")
        if not order_sn:
            raise ChannelError("order has no shopee order_sn in metadata")
        payload = {"order_sn": order_sn,
                   "package_list": [{"order_sn": order_sn, "package_number": tracking or ""}]}
        await self._client().post_json("/logistics/ship_order", json=payload)

    async def reconcile(self) -> dict:
        return {"updated": 0, "skipped": 0}


async def trigger_shopee_poll(db: AsyncSession, adapter: Optional[ShopeeAdapter] = None) -> dict:
    """Webhook trigger — polls and imports via the shared helper ONLY.

    The webhook payload is never read; the poll result is the only data that
    reaches import_channel_orders (polling is the source of truth).
    """
    adapter = adapter or ShopeeAdapter()
    orders = await adapter.import_orders()
    imported = await import_channel_orders(db, ChannelType.SHOPEE.value, orders)
    return {"triggered": True, "fetched": len(orders), "imported": imported}


async def reconcile_shopee(db: AsyncSession, external_status_map: dict[str, str]) -> dict:
    """Apply external status changes with direction rules — never downgrade
    local REFUNDED/CANCELLED back to an earlier state."""
    updated = 0
    skipped = 0
    for order_sn, ext_status in external_status_map.items():
        order = await db.scalar(
            select(Order).where(Order.platform == ChannelType.SHOPEE.value,
                                Order.platform_order_id == order_sn)
        )
        if order is None:
            skipped += 1
            continue
        if order.status in (OrderStatus.REFUNDED, OrderStatus.CANCELLED):
            skipped += 1  # local truth wins
            continue
        target = SHOPEE_STATUS_MAP.get(ext_status)
        if target is None or target == order.status:
            skipped += 1
            continue
        order.status = target
        updated += 1
    await db.commit()
    return {"updated": updated, "skipped": skipped}

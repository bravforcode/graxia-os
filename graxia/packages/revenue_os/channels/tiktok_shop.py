"""TikTok Shop adapter — poll-first order import, sandbox gate.

Same contract as Shopee/Lazada (risk audit #1/#8): polling is the source of
truth, webhooks fail closed and only trigger a poll, mode comes from
ChannelConnection.config and fails closed in production. All outbound calls go
through TikTokClient (the ONLY place signing lives).
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
from .platform_auth import TikTokClient

# TikTok order_status -> local OrderStatus (per-platform map, tested).
TIKTOK_STATUS_MAP = {
    "CANCELLED": OrderStatus.CANCELLED,
    "SHIPPED": OrderStatus.FULFILLED,
    "FULFILLED": OrderStatus.FULFILLED,
}

# Import normalization: AWAITING_SHIPMENT = payment captured -> paid (helper
# fulfills); everything else passes through lowercased (PENDING).
_IMPORT_PAID_STATUSES = {"AWAITING_SHIPMENT", "AWAITING_COLLECTION", "PARTIALLY_SHIPPING"}

REQUIRED_ENV = ("TIKTOK_SHOP_APP_KEY", "TIKTOK_SHOP_APP_SECRET", "TIKTOK_SHOP_SHOP_ID")


class TikTokShopAdapter(ChannelAdapter):
    """TikTok Shop adapter. Credentials from env; mode from config."""

    def __init__(self, config: Optional[dict] = None, http_client: Optional[Any] = None):
        self.config = config or {}
        self._http_client = http_client

    @property
    def name(self) -> ChannelType:
        return ChannelType.TIKTOK_SHOP

    # ── sandbox gate ───────────────────────────────────────────────────
    def _mode(self) -> str:
        mode = self.config.get("mode")
        if mode:
            if mode not in ("sandbox", "live"):
                raise ChannelError(f"TikTok mode must be sandbox|live, got {mode!r}")
            return mode
        if os.getenv("APP_ENV") == "production":
            raise RuntimeError("TikTok channel mode unset in production — refuse to run")
        return "sandbox"

    def _credentials(self) -> dict:
        missing = [v for v in REQUIRED_ENV if not os.getenv(v)]
        if missing:
            if os.getenv("APP_ENV") == "production":
                raise RuntimeError(f"TikTok credentials missing in production: {missing}")
            raise ChannelError(f"TikTok credentials not configured: {missing}")
        return {"app_key": os.getenv("TIKTOK_SHOP_APP_KEY"),
                "app_secret": os.getenv("TIKTOK_SHOP_APP_SECRET"),
                "shop_id": int(os.getenv("TIKTOK_SHOP_SHOP_ID"))}

    def _client(self) -> TikTokClient:
        creds = self._credentials()
        return TikTokClient(
            app_key=creds["app_key"],
            app_secret=creds["app_secret"],
            shop_id=creds["shop_id"],
            mode=self._mode(),
            access_token=os.getenv("TIKTOK_SHOP_ACCESS_TOKEN", ""),
            http_client=self._http_client,
        )

    # ── webhook (fail-closed; poll is the source of truth) ─────────────
    async def verify_webhook(self, request: Any) -> bool:
        # TikTok Shop callback verification is not reliably implementable
        # (risk audit #1). Refuse to trust callbacks; polling is the only
        # import path.
        return False

    async def import_orders(self, since: Optional[str] = None) -> list[dict]:
        body: dict = {"page_size": 50, "order_status": "AWAITING_SHIPMENT"}
        if since:
            try:
                body["update_time_ge"] = int(datetime.fromisoformat(since).timestamp() * 1000)
            except ValueError:
                body["update_time_ge"] = 0
        data = await self._client().post_json("/order/search", json=body)
        out = []
        for o in ((data.get("data") or {}).get("orders", [])):
            payment = o.get("payment_info") or {}
            total = payment.get("total_amount") or {}
            buyer = o.get("buyer_username") or "unknown"
            line = (o.get("line_items") or [{}])[0]
            out.append({
                "platform_order_id": str(o.get("id", "")),
                "customer_email": f"{buyer}@tiktokshop.local",
                "amount_cents": int(Decimal(str(total.get("amount", "0"))) * 100),
                "currency": (total.get("currency") or "THB").upper(),
                "product_id": None,  # item mapping arrives with inventory sync (Task 6)
                "status": "paid" if o.get("order_status") in _IMPORT_PAID_STATUSES
                else str(o.get("order_status", "")).lower(),
                "metadata": {"order_id": o.get("id"), "order_status": o.get("order_status"),
                             "product_id": line.get("product_id")},
            })
        return out

    async def sync_products(self, db: AsyncSession, products: Optional[list] = None) -> int:
        """Push products to TikTok Shop (create / edit by stored product_id)."""
        from ..models import ChannelInventory
        multiplier = float(self.config.get("price_multiplier", 1.0))
        pushed = 0
        for product in (products or []):
            inv = await db.get(ChannelInventory, (ChannelType.TIKTOK_SHOP, product.id))
            stock = inv.channel_stock if inv is not None else 0
            payload = {
                "name": product.name,
                "price": {"amount": f"{Decimal(int(product.price_cents or 0) * multiplier) / 100:.2f}",
                          "currency_code": product.currency or "THB"},
                "sku": [{"stock": stock}],
            }
            if inv is not None and inv.listing_id:
                payload["product_id"] = inv.listing_id
                await self._client().post_json("/product/edit", json=payload)
            else:
                data = await self._client().post_json("/product/create", json=payload)
                product_id = (data.get("data") or {}).get("product_id")
                if inv is None:
                    inv = ChannelInventory(channel=ChannelType.TIKTOK_SHOP, product_id=product.id,
                                           channel_stock=0, stock_buffer=0,
                                           listing_id=str(product_id) if product_id else None)
                    db.add(inv)
                elif product_id:
                    inv.listing_id = str(product_id)
            pushed += 1
        await db.commit()
        return pushed

    async def push_fulfillment(self, order, tracking: Optional[str] = None) -> None:
        order_id = (order.metadata_ or {}).get("order_id")
        if not order_id:
            raise ChannelError("order has no tiktok order_id in metadata")
        await self._client().post_json("/fulfillment/ship", json={
            "order_id": str(order_id),
            "tracking_number": tracking or "",
            "shipping_provider": "OTHER",
        })

    async def reconcile(self) -> dict:
        return {"updated": 0, "skipped": 0}


async def trigger_tiktok_poll(db: AsyncSession, adapter: Optional[TikTokShopAdapter] = None) -> dict:
    """Webhook trigger — polls and imports via the shared helper ONLY."""
    adapter = adapter or TikTokShopAdapter()
    orders = await adapter.import_orders()
    imported = await import_channel_orders(db, ChannelType.TIKTOK_SHOP.value, orders)
    return {"triggered": True, "fetched": len(orders), "imported": imported}


async def reconcile_tiktok(db: AsyncSession, external_status_map: dict[str, str]) -> dict:
    """Apply external status changes with direction rules — never downgrade
    local REFUNDED/CANCELLED back to an earlier state."""
    updated = 0
    skipped = 0
    for order_id, ext_status in external_status_map.items():
        order = await db.scalar(
            select(Order).where(Order.platform == ChannelType.TIKTOK_SHOP.value,
                                Order.platform_order_id == order_id)
        )
        if order is None:
            skipped += 1
            continue
        if order.status in (OrderStatus.REFUNDED, OrderStatus.CANCELLED):
            skipped += 1  # local truth wins
            continue
        target = TIKTOK_STATUS_MAP.get(ext_status)
        if target is None or target == order.status:
            skipped += 1
            continue
        order.status = target
        if target == OrderStatus.REFUNDED:
            from ..finance.refund_sync import ensure_refund_record
            await ensure_refund_record(db, order, reason=f"tiktok {ext_status}")
        updated += 1
    await db.commit()
    return {"updated": updated, "skipped": skipped}

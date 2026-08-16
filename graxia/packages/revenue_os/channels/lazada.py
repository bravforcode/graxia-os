"""Lazada seller-center adapter — poll-first order import, sandbox gate.

Same contract as ShopeeAdapter (risk audit #1/#8): polling is the source of
truth, webhooks fail closed and only trigger a poll, mode comes from
ChannelConnection.config and fails closed in production. All outbound calls go
through LazadaClient (the ONLY place signing lives — no signing copy here).
"""
from __future__ import annotations

import os
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..enums import ChannelType, OrderStatus
from ..models import Order
from .base import ChannelAdapter, ChannelError, import_channel_orders
from .platform_auth import LazadaClient

# Lazada order status -> local OrderStatus (per-platform map, tested).
# delivered is the terminal state, same local target as shipped.
LAZADA_STATUS_MAP = {
    "shipped": OrderStatus.FULFILLED,
    "delivered": OrderStatus.FULFILLED,
    "canceled": OrderStatus.CANCELLED,
    "returned": OrderStatus.REFUNDED,
}

# Import normalization: payment-captured statuses arrive as "paid" so the
# shared helper fulfills them; everything else passes through (PENDING).
_IMPORT_PAID_STATUSES = {"shipped", "ready_to_ship", "packed", "picked", "shipping"}

REQUIRED_ENV = ("LAZADA_APP_KEY", "LAZADA_APP_SECRET", "LAZADA_SELLER_ID")


class LazadaAdapter(ChannelAdapter):
    """Lazada seller-center adapter. Credentials from env; mode from config."""

    def __init__(self, config: Optional[dict] = None, http_client: Optional[Any] = None):
        self.config = config or {}
        self._http_client = http_client

    @property
    def name(self) -> ChannelType:
        return ChannelType.LAZADA

    # ── sandbox gate ───────────────────────────────────────────────────
    def _mode(self) -> str:
        mode = self.config.get("mode")
        if mode:
            if mode not in ("sandbox", "live"):
                raise ChannelError(f"Lazada mode must be sandbox|live, got {mode!r}")
            return mode
        if os.getenv("APP_ENV") == "production":
            raise RuntimeError("Lazada channel mode unset in production — refuse to run")
        return "sandbox"

    def _credentials(self) -> dict:
        missing = [v for v in REQUIRED_ENV if not os.getenv(v)]
        if missing:
            if os.getenv("APP_ENV") == "production":
                raise RuntimeError(f"Lazada credentials missing in production: {missing}")
            raise ChannelError(f"Lazada credentials not configured: {missing}")
        return {"app_key": os.getenv("LAZADA_APP_KEY"), "app_secret": os.getenv("LAZADA_APP_SECRET"),
                "seller_id": os.getenv("LAZADA_SELLER_ID")}

    def _client(self) -> LazadaClient:
        creds = self._credentials()
        return LazadaClient(
            app_key=creds["app_key"],
            app_secret=creds["app_secret"],
            mode=self._mode(),
            seller_id=creds["seller_id"],
            http_client=self._http_client,
        )

    # ── webhook (fail-closed; poll is the source of truth) ─────────────
    async def verify_webhook(self, request: Any) -> bool:
        # Lazada push notifications are not reliably verifiable (risk audit
        # #1). Refuse to trust callbacks; polling is the only import path.
        return False

    async def import_orders(self, since: Optional[str] = None) -> list[dict]:
        params = {"filter": "shipped|ready_to_ship|packed", "sort_by": "updated_at", "limit": "50"}
        if since:
            params["update_after"] = since
        data = await self._client().get_json("/orders/get", params=params)
        out = []
        for o in data.get("data", []):
            statuses = o.get("statuses") or []
            raw_status = (statuses[0] if statuses else "").lower()
            out.append({
                "platform_order_id": str(o.get("order_id", "")),
                "customer_email": o.get("customer_email") or f"{o.get('order_number', 'unknown')}@lazada.local",
                "amount_cents": int(Decimal(str(o.get("price", "0"))) * 100),
                "currency": (o.get("currency") or "THB").upper(),
                "product_id": None,  # item mapping arrives with inventory sync (Task 6)
                "status": "paid" if raw_status in _IMPORT_PAID_STATUSES else raw_status,
                "metadata": {"order_id": o.get("order_id"), "order_number": o.get("order_number"),
                             "order_item_id": _first_item_id(o)},
            })
        return out

    async def sync_products(self) -> int:
        # Wired in the marketplace inventory/price sync task (Task 6).
        return 0

    async def push_fulfillment(self, order, tracking: Optional[str] = None) -> None:
        order_id = (order.metadata_ or {}).get("order_id")
        order_item_id = (order.metadata_ or {}).get("order_item_id")
        if not order_id or not order_item_id:
            raise ChannelError("order lacks lazada order_id/order_item_id in metadata")
        item_list = [{"order_id": str(order_id), "order_item_id": str(order_item_id),
                      "ship_provider": "other", "tracking_number": tracking or ""}]
        await self._client().post_json("/order/pack", json={"order_item_list": item_list})
        await self._client().post_json("/order/ship", json={
            "order_item_list": item_list, "shipping_provider": "other",
            "tracking_number": tracking or ""})

    async def reconcile(self) -> dict:
        return {"updated": 0, "skipped": 0}


def _first_item_id(order: dict) -> Optional[str]:
    items = order.get("items") or []
    if items:
        return items[0].get("order_item_id")
    return None


async def trigger_lazada_poll(db: AsyncSession, adapter: Optional[LazadaAdapter] = None) -> dict:
    """Webhook trigger — polls and imports via the shared helper ONLY."""
    adapter = adapter or LazadaAdapter()
    orders = await adapter.import_orders()
    imported = await import_channel_orders(db, ChannelType.LAZADA.value, orders)
    return {"triggered": True, "fetched": len(orders), "imported": imported}


async def reconcile_lazada(db: AsyncSession, external_status_map: dict[str, str]) -> dict:
    """Apply external status changes with direction rules — never downgrade
    local REFUNDED/CANCELLED back to an earlier state."""
    updated = 0
    skipped = 0
    for order_id, ext_status in external_status_map.items():
        order = await db.scalar(
            select(Order).where(Order.platform == ChannelType.LAZADA.value,
                                Order.platform_order_id == order_id)
        )
        if order is None:
            skipped += 1
            continue
        if order.status in (OrderStatus.REFUNDED, OrderStatus.CANCELLED):
            skipped += 1  # local truth wins
            continue
        target = LAZADA_STATUS_MAP.get(ext_status)
        if target is None or target == order.status:
            skipped += 1
            continue
        order.status = target
        updated += 1
    await db.commit()
    return {"updated": updated, "skipped": skipped}

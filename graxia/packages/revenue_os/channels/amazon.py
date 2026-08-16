"""Amazon SP-API adapter — LWA tokens + role ARN, throttle-aware, PII-safe.

Polling is the source of truth (risk audit #1); SP-API has no reliable seller
webhook import path here, so verify_webhook fails closed and the poll trigger
is the only import path. Mode comes from ChannelConnection.config and fails
closed in production (risk audit #8).

PII RULE: Amazon order payloads carry buyer names/emails/addresses. The
adapter NEVER logs them and never stores them in metadata — normalized orders
keep only the order id and item ids; logs carry order ids only.
"""
from __future__ import annotations

import os
from decimal import Decimal
from typing import Any, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..enums import ChannelType, OrderStatus
from ..models import Order
from .base import ChannelAdapter, ChannelError, import_channel_orders
from .platform_auth import AmazonClient, AmazonTokenCache

logger = structlog.get_logger()

# Amazon OrderStatus -> local OrderStatus (per-platform map, tested).
AMAZON_STATUS_MAP = {
    "CancelPending": OrderStatus.CANCELLED,
    "Canceled": OrderStatus.CANCELLED,
    "Shipped": OrderStatus.FULFILLED,
    "Pending": OrderStatus.PENDING,
}

# Payment-captured statuses arrive as "paid" so the shared helper fulfills.
_IMPORT_PAID_STATUSES = {"Unshipped", "PartiallyShipped", "Shipped"}

REQUIRED_ENV = ("AMAZON_LWA_CLIENT_ID", "AMAZON_LWA_CLIENT_SECRET",
                "AMAZON_SP_API_ROLE_ARN", "AMAZON_SELLER_ID")


class AmazonAdapter(ChannelAdapter):
    """Amazon SP-API seller adapter (MFN). Credentials from env; mode from config."""

    def __init__(self, config: Optional[dict] = None, http_client: Optional[Any] = None):
        self.config = config or {}
        self._http_client = http_client

    @property
    def name(self) -> ChannelType:
        return ChannelType.AMAZON

    # ── sandbox gate ───────────────────────────────────────────────────
    def _mode(self) -> str:
        mode = self.config.get("mode")
        if mode:
            if mode not in ("sandbox", "live"):
                raise ChannelError(f"Amazon mode must be sandbox|live, got {mode!r}")
            return mode
        if os.getenv("APP_ENV") == "production":
            raise RuntimeError("Amazon channel mode unset in production — refuse to run")
        return "sandbox"

    def _credentials(self) -> dict:
        missing = [v for v in REQUIRED_ENV if not os.getenv(v)]
        if missing:
            if os.getenv("APP_ENV") == "production":
                raise RuntimeError(f"Amazon credentials missing in production: {missing}")
            raise ChannelError(f"Amazon credentials not configured: {missing}")
        return {
            "client_id": os.getenv("AMAZON_LWA_CLIENT_ID"),
            "client_secret": os.getenv("AMAZON_LWA_CLIENT_SECRET"),
            "role_arn": os.getenv("AMAZON_SP_API_ROLE_ARN"),
            "seller_id": os.getenv("AMAZON_SELLER_ID"),
        }

    def _client(self) -> AmazonClient:
        creds = self._credentials()
        token_cache = AmazonTokenCache(creds["client_id"], creds["client_secret"],
                                       http_client=self._http_client)
        return AmazonClient(
            token_cache=token_cache,
            role_arn=creds["role_arn"],
            seller_id=creds["seller_id"],
            mode=self._mode(),
            http_client=self._http_client,
        )

    # ── webhook (fail-closed; poll is the source of truth) ─────────────
    async def verify_webhook(self, request: Any) -> bool:
        # No reliable SP-API seller callback import path (risk audit #1).
        return False

    async def import_orders(self, since: Optional[str] = None) -> list[dict]:
        params = {"MarketplaceIds": "ATVPDKIKX0DER", "OrderStatuses": "Unshipped",
                  "MaxResultsPerPage": "50"}
        if since:
            params["LastUpdatedAfter"] = since
        data = await self._client().get_json("/orders/v0/orders", params=params)
        out = []
        order_ids = []
        for o in ((data.get("payload") or {}).get("Orders", [])):
            if o.get("FulfillmentChannel") not in (None, "MFN"):
                continue  # MFN only filter — skip FBA
            total = o.get("OrderTotal") or {}
            out.append({
                "platform_order_id": str(o.get("AmazonOrderId", "")),
                "customer_email": (o.get("BuyerEmail") or
                                   f"{o.get('AmazonOrderId', 'unknown')}@amazon.local"),
                "amount_cents": int(Decimal(str(total.get("Amount", "0"))) * 100),
                "currency": (total.get("CurrencyCode") or "THB").upper(),
                "product_id": None,  # item mapping arrives with inventory sync (Task 6)
                "status": "paid" if o.get("OrderStatus") in _IMPORT_PAID_STATUSES
                else str(o.get("OrderStatus", "")).lower(),
                # metadata carries NO PII — order id + item ids only
                "metadata": {"amazon_order_id": o.get("AmazonOrderId"),
                             "order_item_ids": [i.get("OrderItemId") for i in o.get("OrderItems", [])]},
            })
            order_ids.append(str(o.get("AmazonOrderId", "")))
        logger.info("amazon_orders_fetched", count=len(out), order_ids=order_ids)  # ids only
        return out

    async def sync_products(self, db: AsyncSession, products: Optional[list] = None) -> int:
        """Push price/name for SKU-mapped Amazon listings (Listings Items API
        PATCH). Requires ChannelInventory.listing_id = seller SKU; products
        without a SKU mapping are skipped (no silent create — SP-API catalog
        creation needs category attributes, wired at deployment)."""
        from ..models import ChannelInventory
        multiplier = float(self.config.get("price_multiplier", 1.0))
        pushed = 0
        skipped = 0
        for product in (products or []):
            inv = await db.get(ChannelInventory, (ChannelType.AMAZON, product.id))
            if inv is None or not inv.listing_id:
                skipped += 1  # needs listing_id as the seller SKU
                continue
            payload = {
                "productType": "GENERIC",
                "attributes": {
                    "item_name": [{"value": product.name, "language_tag": "en-US"}],
                    "list_price": [{"value": f"{Decimal(int(product.price_cents or 0) * multiplier) / 100:.2f}",
                                    "currency": "USD"}],
                },
            }
            await self._client().patch_json(
                f"/listings/2021-08-01/items/{self._seller_id()}/{inv.listing_id}", json=payload)
            pushed += 1
        await db.commit()
        logger.info("amazon_products_synced", pushed=pushed, skipped=skipped)
        return pushed

    def _seller_id(self) -> str:
        return os.getenv("AMAZON_SELLER_ID", "")

    async def push_fulfillment(self, order, tracking: Optional[str] = None) -> None:
        amazon_order_id = (order.metadata_ or {}).get("amazon_order_id")
        if not amazon_order_id:
            raise ChannelError("order has no amazon_order_id in metadata")
        payload: dict = {"CarrierCode": "Other", "TrackingNumber": tracking or ""}
        item_ids = (order.metadata_ or {}).get("order_item_ids") or []
        if item_ids:
            payload["OrderItems"] = [{"OrderItemId": str(i)} for i in item_ids]
        await self._client().post_json(f"/orders/v0/orders/{amazon_order_id}/shipment", json=payload)
        logger.info("amazon_shipment_pushed", amazon_order_id=amazon_order_id)  # id only

    async def reconcile(self) -> dict:
        return {"updated": 0, "skipped": 0}


async def trigger_amazon_poll(db: AsyncSession, adapter: Optional[AmazonAdapter] = None) -> dict:
    """Webhook trigger — polls and imports via the shared helper ONLY."""
    adapter = adapter or AmazonAdapter()
    orders = await adapter.import_orders()
    imported = await import_channel_orders(db, ChannelType.AMAZON.value, orders)
    return {"triggered": True, "fetched": len(orders), "imported": imported}


async def reconcile_amazon(db: AsyncSession, external_status_map: dict[str, str]) -> dict:
    """Apply external status changes with direction rules — never downgrade
    local REFUNDED/CANCELLED back to an earlier state."""
    updated = 0
    skipped = 0
    for order_id, ext_status in external_status_map.items():
        order = await db.scalar(
            select(Order).where(Order.platform == ChannelType.AMAZON.value,
                                Order.platform_order_id == order_id)
        )
        if order is None:
            skipped += 1
            continue
        if order.status in (OrderStatus.REFUNDED, OrderStatus.CANCELLED):
            skipped += 1  # local truth wins
            continue
        target = AMAZON_STATUS_MAP.get(ext_status)
        if target is None or target == order.status:
            skipped += 1
            continue
        order.status = target
        if target == OrderStatus.REFUNDED:
            from ..finance.refund_sync import ensure_refund_record
            await ensure_refund_record(db, order, reason=f"amazon {ext_status}")
        updated += 1
    await db.commit()
    return {"updated": updated, "skipped": skipped}

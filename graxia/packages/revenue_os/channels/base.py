"""Channel adapter framework — one adapter per external commerce surface.

Also hosts the ONE shared order-import path (`import_channel_orders`) used by
every adapter — idempotent via (platform, platform_order_id) unique constraint.
"""
from __future__ import annotations

import abc
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..enums import ChannelType, IncidentSeverity, OrderStatus
from ..models import IncidentEvent, Order, Product
from ..services.fulfillment_service import FulfillmentService


class ChannelError(Exception):
    """Raised when an external channel call fails (network, auth, 4xx/5xx)."""


class ChannelAdapter(abc.ABC):
    """Contract every channel must implement. All methods are async."""

    @property
    @abc.abstractmethod
    def name(self) -> ChannelType:
        ...

    @abc.abstractmethod
    async def verify_webhook(self, request: Any) -> bool:
        """Verify the inbound webhook signature BEFORE deserialization."""

    @abc.abstractmethod
    async def import_orders(self, since: Optional[str] = None) -> list[dict]:
        """Return normalized orders: {platform_order_id, customer_email,
        amount_cents, currency, product_id (if mappable), status, metadata}."""

    @abc.abstractmethod
    async def sync_products(self, db: AsyncSession, products: Optional[list] = None) -> int:
        """Push local published products to the channel; return count pushed.

        products: optional list of Product rows. The adapter persists the
        channel-side listing id on the ChannelInventory row (via db) so
        re-pushes update instead of duplicate-create.
        """

    @abc.abstractmethod
    async def push_fulfillment(self, order, tracking: Optional[str] = None) -> None:
        """Mark order fulfilled (or push tracking number)."""

    @abc.abstractmethod
    async def reconcile(self) -> dict:
        """Apply external status changes to local orders; return {updated, skipped}."""


async def import_channel_orders(db: AsyncSession, platform: str, orders: list[dict]) -> int:
    """Idempotent import for ANY channel (platform+platform_order_id unique).

    - Unknown product -> IncidentEvent LOW (order skipped, nothing imported)
    - status in ("paid", "PAID") -> OrderStatus.PAID and fulfillment queued
    - Re-running with the same orders imports nothing (idempotent)
    """
    imported = 0
    for data in orders:
        existing = await db.scalar(
            select(Order).where(Order.platform == platform,
                                Order.platform_order_id == data["platform_order_id"])
        )
        if existing:
            continue
        product = None
        if data.get("product_id"):
            product = await db.get(Product, data["product_id"])
        if product is None:
            db.add(IncidentEvent(
                title=f"{platform} order unmappable: {data['platform_order_id']}",
                description="no graxia product_id on the order line item",
                severity=IncidentSeverity.LOW,
            ))
            await db.flush()
            continue
        order = Order(
            platform=platform,
            platform_order_id=data["platform_order_id"],
            customer_email=data["customer_email"],
            product_id=product.id,
            amount_cents=data["amount_cents"],
            currency=data["currency"],
            status=OrderStatus.PAID if data.get("status") in ("paid", "PAID") else OrderStatus.PENDING,
            metadata_={**data.get("metadata", {})},
        )
        db.add(order)
        await db.flush()
        imported += 1
        if order.status == OrderStatus.PAID:
            await FulfillmentService.fulfill_order(db, order.id, auto_queue_email=True)
    await db.commit()
    return imported

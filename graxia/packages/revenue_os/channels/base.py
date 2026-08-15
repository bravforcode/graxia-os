"""Channel adapter framework — one adapter per external commerce surface."""
from __future__ import annotations

import abc
from typing import Any, Optional

from ..enums import ChannelType


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
    async def sync_products(self) -> int:
        """Push local published products to the channel; return count."""

    @abc.abstractmethod
    async def push_fulfillment(self, order, tracking: Optional[str] = None) -> None:
        """Mark order fulfilled (or push tracking number)."""

    @abc.abstractmethod
    async def reconcile(self) -> dict:
        """Apply external status changes to local orders; return {updated, skipped}."""

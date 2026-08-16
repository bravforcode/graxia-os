"""Marketplace order poll — all marketplace adapters, lock-wrapped.

Polling is the source of truth (risk audit #1): each connected marketplace
channel is polled through its adapter, imported via the shared
import_channel_orders helper, and reconciled with the per-platform status map.
Channels without a ChannelConnection row (or disabled) are skipped; per-channel
errors are captured so one failing platform never blocks the others.
"""
from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from ...db import get_db_session
from ...core.db_ops import acquire_automation_lock
from ...enums import ChannelType
from ...models import ChannelConnection
from ...channels.base import import_channel_orders
from ...channels.shopee import ShopeeAdapter, reconcile_shopee
from ...channels.lazada import LazadaAdapter, reconcile_lazada
from ...channels.tiktok_shop import TikTokShopAdapter, reconcile_tiktok
from ...channels.amazon import AmazonAdapter, reconcile_amazon

logger = structlog.get_logger()

LOCK_NAME = "marketplace_poll"

ADAPTERS = {
    ChannelType.SHOPEE: (ShopeeAdapter, reconcile_shopee),
    ChannelType.LAZADA: (LazadaAdapter, reconcile_lazada),
    ChannelType.TIKTOK_SHOP: (TikTokShopAdapter, reconcile_tiktok),
    ChannelType.AMAZON: (AmazonAdapter, reconcile_amazon),
}


async def marketplace_poll_with_db(db: AsyncSession) -> dict:
    async with acquire_automation_lock(db, LOCK_NAME, ttl_seconds=600) as acquired:
        if not acquired:
            return {"skipped": True, "reason": "lock_held_by_another_worker"}
        results: dict = {}
        for channel, (adapter_cls, reconcile_fn) in ADAPTERS.items():
            conn = await db.scalar(
                select(ChannelConnection).where(ChannelConnection.channel == channel))
            if conn is None or not conn.enabled:
                results[channel.value] = {"skipped": True, "reason": "not_connected"}
                continue
            config = conn.config or {}
            adapter = adapter_cls(config=config)
            try:
                orders = await adapter.import_orders(config.get("last_import_at"))
                imported = await import_channel_orders(db, channel.value, orders)
                external = {o["platform_order_id"]: o["status"] for o in orders}
                reconcile = await reconcile_fn(db, external)
                conn.config = {**config, "last_import_at": datetime.now(timezone.utc).isoformat()}
                conn.last_sync_at = datetime.now(timezone.utc)
                results[channel.value] = {"fetched": len(orders), "imported": imported,
                                          "reconcile": reconcile}
            except Exception as exc:
                logger.exception("marketplace_poll_failed", channel=channel.value, err=str(exc))
                results[channel.value] = {"skipped": True, "reason": f"error: {exc}"}
        await db.commit()
        return {"skipped": False, "channels": results}


def marketplace_poll():
    import asyncio

    async def _impl():
        async with get_db_session() as db:
            return await marketplace_poll_with_db(db)

    return asyncio.run(_impl())

"""Shopify sync: order import + reconcile (lock-wrapped)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db_session
from ...core.db_ops import acquire_automation_lock
from ...enums import ChannelType
from ...models import ChannelConnection
from ...channels import shopify as shopify_mod

logger = structlog.get_logger()

LOCK_NAME = "shopify_sync"


async def shopify_sync_with_db(db: AsyncSession) -> dict:
    async with acquire_automation_lock(db, LOCK_NAME, ttl_seconds=600) as acquired:
        if not acquired:
            return {"skipped": True, "reason": "lock_held_by_another_worker"}
        # cursor: last successful import time (kept in ChannelConnection config)
        conn = await db.scalar(
            select(ChannelConnection).where(ChannelConnection.channel == ChannelType.SHOPIFY)
        )
        since = None
        if conn is not None and conn.config.get("last_import_at"):
            since = conn.config["last_import_at"]

        adapter = shopify_mod.ShopifyAdapter()
        try:
            orders = await adapter.import_orders(since)
        except Exception as exc:
            logger.exception("shopify_import_failed", err=str(exc))
            return {"skipped": True, "reason": f"import_failed: {exc}"}

        imported = await shopify_mod.import_shopify_orders(db, orders)
        external = {o["platform_order_id"]: o["status"] for o in orders}
        reconcile = await shopify_mod.reconcile_shopify(db, external)

        now = datetime.now(timezone.utc).isoformat()
        if conn is None:
            conn = ChannelConnection(channel=ChannelType.SHOPIFY, name="main-store", config={"last_import_at": now})
            db.add(conn)
        else:
            conn.config = {**(conn.config or {}), "last_import_at": now}
            conn.last_sync_at = datetime.now(timezone.utc)
        await db.commit()
        return {"skipped": False, "fetched": len(orders), "imported": imported, "reconcile": reconcile}


def shopify_sync():
    import asyncio

    async def _impl():
        async with get_db_session() as db:
            return await shopify_sync_with_db(db)

    return asyncio.run(_impl())

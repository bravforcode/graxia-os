"""Marketplace inventory + price sync (lock-wrapped)."""
from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db_session
from ...core.db_ops import acquire_automation_lock
from ...channels.marketplace_sync import inventory_reconcile, price_sync

logger = structlog.get_logger()

LOCK_NAME = "inventory_sync"


async def inventory_sync_with_db(db: AsyncSession) -> dict:
    async with acquire_automation_lock(db, LOCK_NAME, ttl_seconds=600) as acquired:
        if not acquired:
            return {"skipped": True, "reason": "lock_held_by_another_worker"}
        inv = await inventory_reconcile(db)
        prices = await price_sync(db)
        return {"skipped": False, "inventory": inv, "prices": prices}


def inventory_sync():
    import asyncio

    async def _impl():
        async with get_db_session() as db:
            return await inventory_sync_with_db(db)

    return asyncio.run(_impl())

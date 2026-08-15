"""Supplier (POD) status polling — lock-wrapped."""
from __future__ import annotations

import structlog

from ...db import get_db_session
from ...core.db_ops import acquire_automation_lock
from ...channels.supplier_pod import SupplierPODAdapter

logger = structlog.get_logger()

LOCK_NAME = "supplier_poll"


async def supplier_poll_with_db(db):
    async with acquire_automation_lock(db, LOCK_NAME, ttl_seconds=600) as acquired:
        if not acquired:
            return {"skipped": True, "reason": "lock_held_by_another_worker"}
        return await SupplierPODAdapter().poll(db)


def supplier_poll():
    import asyncio

    async def _impl():
        async with get_db_session() as db:
            return await supplier_poll_with_db(db)

    return asyncio.run(_impl())

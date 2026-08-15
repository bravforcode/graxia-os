"""Process pending refunds against payment providers (lock-wrapped — Risk Audit #8)."""
from __future__ import annotations

from ...db import get_db_session
from ...core.db_ops import acquire_automation_lock
from ...services.refund_executor import RefundExecutor

LOCK_NAME = "process_refunds"


async def process_refunds_with_db(db):
    async with acquire_automation_lock(db, LOCK_NAME, ttl_seconds=600) as acquired:
        if not acquired:
            return {"skipped": True, "reason": "lock_held_by_another_worker"}
        return await RefundExecutor.process_pending_refunds(db)


def process_refunds():
    import asyncio

    async def _impl():
        async with get_db_session() as db:
            return await process_refunds_with_db(db)

    return asyncio.run(_impl())

"""Daily FX rate refresh (lock-wrapped) — feeds FX-aware ABSOLUTE caps."""
from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db_session
from ...core.db_ops import acquire_automation_lock
from ...channels.marketplace_sync import fx_refresh as fx_refresh_rates

logger = structlog.get_logger()

LOCK_NAME = "fx_refresh"


async def fx_refresh_with_db(db: AsyncSession) -> dict:
    async with acquire_automation_lock(db, LOCK_NAME, ttl_seconds=600) as acquired:
        if not acquired:
            return {"skipped": True, "reason": "lock_held_by_another_worker"}
        try:
            count = await fx_refresh_rates(db)
        except Exception as exc:
            logger.exception("fx_refresh_failed", err=str(exc))
            return {"skipped": False, "error": str(exc)}
        return {"skipped": False, "rates": count}


def fx_refresh():
    import asyncio

    async def _impl():
        async with get_db_session() as db:
            return await fx_refresh_with_db(db)

    return asyncio.run(_impl())

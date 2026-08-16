"""Competitor repricing cycle (lock-wrapped) — shared price path."""
from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db_session
from ...core.db_ops import acquire_automation_lock
from ...pricing.repricing import provider_from_env, repricing_cycle

logger = structlog.get_logger()

LOCK_NAME = "repricing"


async def repricing_with_db(db: AsyncSession) -> dict:
    async with acquire_automation_lock(db, LOCK_NAME, ttl_seconds=600) as acquired:
        if not acquired:
            return {"skipped": True, "reason": "lock_held_by_another_worker"}
        provider = provider_from_env()
        if provider is None:
            return {"skipped": True, "reason": "no_provider_configured"}
        try:
            observations = await provider.get_competitor_prices()
        except Exception as exc:
            logger.exception("repricing_fetch_failed", err=str(exc))
            return {"skipped": True, "reason": f"fetch_failed: {exc}"}
        return {"skipped": False, **await repricing_cycle(db, observations)}


def repricing():
    import asyncio

    async def _impl():
        async with get_db_session() as db:
            return await repricing_with_db(db)

    return asyncio.run(_impl())

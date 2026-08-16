"""Daily affiliate payout review (lock-wrapped) — flags threshold rows + Telegram."""
from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db_session
from ...core.db_ops import acquire_automation_lock
from ...affiliate.service import review_payouts

logger = structlog.get_logger()

LOCK_NAME = "affiliate_review"


async def affiliate_review_with_db(db: AsyncSession) -> dict:
    async with acquire_automation_lock(db, LOCK_NAME, ttl_seconds=600) as acquired:
        if not acquired:
            return {"skipped": True, "reason": "lock_held_by_another_worker"}
        from graxia.services.telegram_notifier import UnifiedTelegramNotifier
        return {"skipped": False, **await review_payouts(db, notifier=UnifiedTelegramNotifier)}


def affiliate_review():
    import asyncio

    async def _impl():
        async with get_db_session() as db:
            return await affiliate_review_with_db(db)

    return asyncio.run(_impl())

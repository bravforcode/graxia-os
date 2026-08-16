"""Daily growth digest (lock-wrapped) — opportunity scan -> Telegram."""
from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db_session
from ..core.db_ops import acquire_automation_lock
from ..growth.opportunity import _digest_text, opportunity_scan

logger = structlog.get_logger()

LOCK_NAME = "growth_digest"


async def growth_digest_with_db(db: AsyncSession, notifier=None) -> dict:
    async with acquire_automation_lock(db, LOCK_NAME, ttl_seconds=600) as acquired:
        if not acquired:
            return {"skipped": True, "reason": "lock_held_by_another_worker"}
        scan = await opportunity_scan(db)
        text = _digest_text(scan)
        if notifier is not None:
            try:
                await notifier().send_message(text=text)
            except Exception:
                logger.exception("growth_digest_telegram_failed")
        return {"skipped": False, "recommendations": len(scan["recommendations"]),
                "digest": text}


def growth_digest():
    import asyncio

    async def _impl():
        async with get_db_session() as db:
            from graxia.services.telegram_notifier import UnifiedTelegramNotifier
            return await growth_digest_with_db(db, notifier=UnifiedTelegramNotifier)

    return asyncio.run(_impl())

"""Marketplace payout reconciliation (lock-wrapped) — settlements -> ledger."""
from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db_session
from ...core.db_ops import acquire_automation_lock
from ...finance.payout_recon import PayoutProvider, provider_from_env, reconcile_payouts
from ...enums import ChannelType

logger = structlog.get_logger()

LOCK_NAME = "payout_recon"

MARKETPLACE_PLATFORMS = [ChannelType.SHOPEE.value, ChannelType.LAZADA.value,
                         ChannelType.TIKTOK_SHOP.value, ChannelType.AMAZON.value]


async def payout_recon_with_db(db: AsyncSession) -> dict:
    async with acquire_automation_lock(db, LOCK_NAME, ttl_seconds=600) as acquired:
        if not acquired:
            return {"skipped": True, "reason": "lock_held_by_another_worker"}
        provider: PayoutProvider = provider_from_env()
        if provider is None:
            return {"skipped": True, "reason": "no_provider_configured"}
        results: dict = {}
        for platform in MARKETPLACE_PLATFORMS:
            try:
                settlements = await provider.fetch_settlements(platform)
                results[platform] = await reconcile_payouts(db, platform, settlements)
            except Exception as exc:
                logger.exception("payout_recon_failed", platform=platform, err=str(exc))
                results[platform] = {"skipped": True, "reason": f"error: {exc}"}
        await db.commit()
        return {"skipped": False, "platforms": results}


def payout_recon():
    import asyncio

    async def _impl():
        async with get_db_session() as db:
            return await payout_recon_with_db(db)

    return asyncio.run(_impl())

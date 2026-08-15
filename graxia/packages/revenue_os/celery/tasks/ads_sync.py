"""Ads sync: metrics pull + policy-gated optimization (lock-wrapped)."""
from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db_session
from ...core.db_ops import acquire_automation_lock
from ...core.policy_engine import PolicyEngine
from ...enums import AutonomyMode
from ...models import AdCampaignSync
from ...ads.meta import MetaAdsClient, sync_ads_metrics
from ...agents.commerce_ops import CommerceOpsAgent

logger = structlog.get_logger()

LOCK_NAME = "ads_sync"


async def ads_sync_with_db(db: AsyncSession) -> dict:
    async with acquire_automation_lock(db, LOCK_NAME, ttl_seconds=600) as acquired:
        if not acquired:
            return {"skipped": True, "reason": "lock_held_by_another_worker"}
        mode = await PolicyEngine.get_autonomy_mode(db)
        # Metrics sync is read-only — safe in every mode
        client = MetaAdsClient()
        try:
            campaigns = await client.list_campaigns()
            ids = [c["platform_campaign_id"] for c in campaigns]
            metrics = await client.get_metrics(ids) if ids else {}
        except Exception as exc:
            logger.exception("ads_metrics_failed", err=str(exc))
            return {"skipped": True, "reason": f"metrics_failed: {exc}"}
        status_map = {c["platform_campaign_id"]: c.get("status") or "ACTIVE" for c in campaigns}
        for cid, m in metrics.items():
            m["status"] = status_map.get(cid, "ACTIVE")
        synced = await sync_ads_metrics(db, "meta", metrics)
        # Optimization is owned by the commerce cycle (single owner, one lock).
        # ads_sync ONLY refreshes metrics — budgets are never touched here.
        await db.commit()
        return {"skipped": False, "synced": synced}


def ads_sync():
    import asyncio

    async def _impl():
        async with get_db_session() as db:
            return await ads_sync_with_db(db)

    return asyncio.run(_impl())

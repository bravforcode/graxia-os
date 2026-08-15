"""Commerce ops agent celery task - lock-wrapped (Risk Audit #8)."""
from __future__ import annotations

import structlog

from ...db import get_db_session
from ...core.db_ops import acquire_automation_lock
from ...agents.commerce_ops import CommerceOpsAgent

logger = structlog.get_logger()

LOCK_NAME = "commerce_ops"


async def commerce_ops_with_db(db):
    async with acquire_automation_lock(db, LOCK_NAME, ttl_seconds=600) as acquired:
        if not acquired:
            return {"skipped": True, "reason": "lock_held_by_another_worker"}
        return await CommerceOpsAgent.run_cycle(db)


def commerce_ops():
    """Run the autonomous commerce cycle. Follows agent_consumers asyncio pattern."""
    import asyncio

    async def _impl():
        async with get_db_session() as db:
            return await commerce_ops_with_db(db)

    return asyncio.run(_impl())

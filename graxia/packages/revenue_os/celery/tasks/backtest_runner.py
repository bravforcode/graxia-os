"""Nightly backtest — lock-wrapped; writes a StrategyLog summary only."""
from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db_session
from ...core.db_ops import acquire_automation_lock
from ...core.policy_engine import PolicyEngine
from ...enums import AutonomyMode
from ...models import StrategyLog
from ...simulation.backtest import run_backtest

logger = structlog.get_logger()

LOCK_NAME = "backtest_runner"


async def backtest_runner_with_db(db: AsyncSession) -> dict:
    async with acquire_automation_lock(db, LOCK_NAME, ttl_seconds=600) as acquired:
        if not acquired:
            return {"skipped": True, "reason": "lock_held_by_another_worker"}
        mode = await PolicyEngine.get_autonomy_mode(db)
        if mode == AutonomyMode.OFF:
            return {"skipped": True, "reason": "autonomy_off"}
        report = await run_backtest(db, days=30)
        db.add(StrategyLog(
            week_start=datetime_utcnow_date(),
            summary=f"Backtest: {report['decisions']} decisions ({report['allowed']} allowed / {report['denied']} denied), "
                    f"est impact {report['est_revenue_impact_cents'] / 100:.2f} (ESTIMATE)",
            recommendations="See backtest report for per-action breakdown.",
        ))
        await db.commit()
        return {"skipped": False, **report}


def datetime_utcnow_date():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).date()


def backtest_runner():
    import asyncio

    async def _impl():
        async with get_db_session() as db:
            return await backtest_runner_with_db(db)

    return asyncio.run(_impl())

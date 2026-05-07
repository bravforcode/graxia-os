"""Scheduled platform maintenance tasks."""
from __future__ import annotations

import asyncio
import logging

from app.config import settings
from app.tasks.base import execute_managed_async_task, idempotent_task
from app.tasks.celery_app import celery_app
from app.tasks.dlq_handler import DeadLetterQueue
from app.tasks.queues import BACKGROUND_QUEUE, CRITICAL_QUEUE, DEFAULT_QUEUE

logger = logging.getLogger(__name__)


async def run_weekly_strategy() -> dict[str, str]:
    from app.agents.strategy_agent import StrategyAgent

    agent = StrategyAgent()
    await agent.run()
    return {"status": "completed"}


async def run_identity_snapshot() -> dict[str, str]:
    from app.core.identity import identity

    await identity.maybe_snapshot_identity()
    return {"status": "completed"}


async def run_obsidian_daily_note() -> dict[str, str]:
    from app.integrations.obsidian import build_obsidian_connector

    if build_obsidian_connector() is None:
        return {"status": "skipped"}

    from app.agents.obsidian_sync import obsidian_sync_agent

    await obsidian_sync_agent.create_daily_note()
    return {"status": "completed"}


async def run_obsidian_refresh() -> dict[str, str]:
    from app.integrations.obsidian import build_obsidian_connector

    if build_obsidian_connector() is None:
        return {"status": "skipped"}

    from app.agents.obsidian_sync import obsidian_sync_agent

    await obsidian_sync_agent.bootstrap_second_brain()
    return {"status": "completed"}


async def check_dlq_depth() -> dict[str, int]:
    queue = DeadLetterQueue()
    depth = await queue.get_depth()
    logger.info("DLQ depth check: %s", depth)
    return {"depth": depth}


async def run_autopilot_cycle() -> dict[str, object]:
    if not settings.AUTOPILOT_ENABLED:
        return {"status": "skipped"}

    from app.telegram_bot.bot import send_message

    errors: list[str] = []
    competitions = 0
    leads = 0
    discovered_jobs = 0
    new_jobs = 0

    try:
        from app.agents.competition_scout import CompetitionScout

        competitions = int(await CompetitionScout().run())
    except Exception as exc:
        errors.append(f"competition_scout: {str(exc)[:120]}")

    try:
        from app.agents.lead_hunter import LeadHunter

        leads = int(await LeadHunter().run())
    except Exception as exc:
        errors.append(f"lead_hunter: {str(exc)[:120]}")

    try:
        from app.agents.job_hunter import job_hunter_agent

        result = await job_hunter_agent.run()
        discovered_jobs = int(result.get("discovered", 0) or 0)
        new_jobs = int(result.get("new", 0) or 0)
    except Exception as exc:
        errors.append(f"job_hunter: {str(exc)[:120]}")

    scraper_alerts: list[str] = []
    try:
        from sqlalchemy import desc, select

        from app.database import AsyncSessionLocal
        from app.models.scraper_health import ScraperHealth

        async with AsyncSessionLocal() as db:
            rows = list(
                (
                    await db.execute(
                        select(ScraperHealth)
                        .where(
                            (ScraperHealth.consecutive_failures.is_not(None) & (ScraperHealth.consecutive_failures > 0))
                            | (ScraperHealth.is_muted.is_(True))
                        )
                        .order_by(desc(ScraperHealth.consecutive_failures), desc(ScraperHealth.updated_at))
                        .limit(8)
                    )
                )
                .scalars()
                .all()
            )
        for row in rows:
            failures = int(row.consecutive_failures or 0)
            muted = bool(row.is_muted)
            last_error = (row.last_error or "").strip().replace("\n", " ")
            suffix = " (muted)" if muted else ""
            if last_error:
                scraper_alerts.append(f"{row.source_name}: {failures}x{suffix} — {last_error[:80]}")
            else:
                scraper_alerts.append(f"{row.source_name}: {failures}x{suffix}")
    except Exception as exc:
        errors.append(f"scraper_health: {str(exc)[:120]}")

    should_notify = bool(errors) or competitions > 0 or leads > 0 or new_jobs > 0 or settings.AUTOPILOT_NOTIFY_EVERY_RUN
    if should_notify:
        lines = [
            "🤖 Autopilot cycle",
            f"• Competitions found: {competitions}",
            f"• Leads found: {leads}",
            f"• Jobs new: {new_jobs} (discovered {discovered_jobs})",
        ]
        if scraper_alerts:
            lines.append("🕷️ Scrapers:")
            for item in scraper_alerts[:6]:
                lines.append(f"• {item}")
        if errors:
            lines.append("⚠️ Errors:")
            for err in errors[:5]:
                lines.append(f"• {err}")
        await send_message("\n".join(lines), parse_mode="HTML")

    status = "degraded" if errors else "ok"
    return {
        "status": status,
        "competitions": competitions,
        "leads": leads,
        "jobs_discovered": discovered_jobs,
        "jobs_new": new_jobs,
        "scraper_alerts": scraper_alerts,
        "errors": errors,
    }


@celery_app.task(name="tasks.maintenance.weekly_strategy", queue=DEFAULT_QUEUE)
@idempotent_task("{task_name}:{date}")
def weekly_strategy_task():
    return execute_managed_async_task(
        task_name="weekly_strategy",
        queue=DEFAULT_QUEUE,
        coroutine_factory=run_weekly_strategy,
    )


@celery_app.task(name="tasks.maintenance.identity_snapshot", queue=DEFAULT_QUEUE)
@idempotent_task("{task_name}:{date}")
def identity_snapshot_task():
    return execute_managed_async_task(
        task_name="identity_snapshot",
        queue=DEFAULT_QUEUE,
        coroutine_factory=run_identity_snapshot,
    )


@celery_app.task(name="tasks.maintenance.obsidian_daily_note", queue=BACKGROUND_QUEUE)
@idempotent_task("{task_name}:{date}")
def obsidian_daily_note_task():
    return execute_managed_async_task(
        task_name="obsidian_daily_note",
        queue=BACKGROUND_QUEUE,
        coroutine_factory=run_obsidian_daily_note,
    )


@celery_app.task(name="tasks.maintenance.obsidian_refresh", queue=BACKGROUND_QUEUE)
@idempotent_task("{task_name}:{date}")
def obsidian_refresh_task():
    return execute_managed_async_task(
        task_name="obsidian_refresh",
        queue=BACKGROUND_QUEUE,
        coroutine_factory=run_obsidian_refresh,
    )


@celery_app.task(name="tasks.maintenance.check_dlq_depth", queue=CRITICAL_QUEUE)
def dlq_depth_task():
    return asyncio.run(check_dlq_depth())


@celery_app.task(name="tasks.maintenance.autopilot_cycle", queue=DEFAULT_QUEUE)
@idempotent_task("{task_name}:{date}", lock_ttl=1800)
def autopilot_cycle_task():
    return execute_managed_async_task(
        task_name="autopilot_cycle",
        queue=DEFAULT_QUEUE,
        coroutine_factory=run_autopilot_cycle,
    )

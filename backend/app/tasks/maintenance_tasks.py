"""Scheduled platform maintenance tasks."""
from __future__ import annotations

import asyncio
import logging

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
    from app.agents.obsidian_sync import obsidian_sync_agent

    await obsidian_sync_agent.create_daily_note()
    return {"status": "completed"}


async def run_obsidian_refresh() -> dict[str, str]:
    from app.agents.obsidian_sync import obsidian_sync_agent

    await obsidian_sync_agent.bootstrap_second_brain()
    return {"status": "completed"}


async def check_dlq_depth() -> dict[str, int]:
    queue = DeadLetterQueue()
    depth = await queue.get_depth()
    logger.info("DLQ depth check: %s", depth)
    return {"depth": depth}


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

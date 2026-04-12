"""Celery task: scan vault for user edits and sync back to DB.

Runs every 30 minutes.
"""
import asyncio
import logging
from typing import Any, TypedDict

from app.tasks.base import execute_managed_async_task
from app.tasks.celery_app import celery_app
from app.tasks.queues import BACKGROUND_QUEUE

logger = logging.getLogger(__name__)


class VaultSyncResult(TypedDict):
    synced_count: int
    failed_count: int


async def run_vault_sync() -> VaultSyncResult:
    """Run vault reader agent to scan and sync changes."""
    from app.agents.vault_reader import VaultReaderAgent

    agent = VaultReaderAgent()
    result = await agent.sync_vault_changes()

    synced = result.get("synced_count", 0)
    failed = result.get("failed_count", 0)

    logger.info("vault_sync_complete", synced_count=synced, failed_count=failed)
    return {"synced_count": synced, "failed_count": failed}


@celery_app.task(name="tasks.vault_sync", queue=BACKGROUND_QUEUE)
def vault_sync_task() -> VaultSyncResult:
    """Celery task wrapper for vault sync."""
    return execute_managed_async_task(
        task_name="vault_sync",
        queue=BACKGROUND_QUEUE,
        coroutine_factory=run_vault_sync,
    )

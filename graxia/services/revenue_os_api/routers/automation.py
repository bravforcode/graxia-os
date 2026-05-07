"""
graxia/services/revenue_os_api/routers/automation.py
Celery task management endpoints — trigger tasks on demand, inspect locks.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
# fastapi.responses not needed — no 204 no-content routes
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.db import get_db
from ....packages.revenue_os.models import AutomationLock
from ..dependencies import require_admin_api_key

router = APIRouter()
logger = logging.getLogger(__name__)

_ALLOWED_TASKS = {
    "daily_revenue_ops",
    "hourly_monitor",
    "send_pending_emails",
    "campaign_engine",
    "weekly_review",
}


@router.get(
    "/locks",
    dependencies=[Depends(require_admin_api_key)],
    summary="List active distributed automation locks",
)
async def list_locks(db: AsyncSession = Depends(get_db)) -> list[dict]:
    result = await db.scalars(select(AutomationLock))
    return [
        {
            "lock_name": lock.lock_name,
            "locked_by_worker": lock.locked_by_worker,
            "acquired_at": lock.acquired_at.isoformat(),
            "expires_at": lock.expires_at.isoformat(),
            "heartbeat_at": lock.heartbeat_at.isoformat() if lock.heartbeat_at else None,
        }
        for lock in result
    ]


@router.delete(
    "/locks/{lock_name}",
    status_code=200,
    dependencies=[Depends(require_admin_api_key)],
    summary="Force-release a stuck automation lock (emergency use only)",
)
async def force_release_lock(
    lock_name: str, db: AsyncSession = Depends(get_db)
) -> dict:
    """Delete a stuck lock row. Returns {released, lock_name} for audit log."""
    result = await db.execute(
        delete(AutomationLock).where(AutomationLock.lock_name == lock_name)
    )
    released = result.rowcount > 0
    logger.warning("Force-released automation lock: %s (found=%s)", lock_name, released)
    return {"released": released, "lock_name": lock_name}


@router.post(
    "/trigger/{task_name}",
    dependencies=[Depends(require_admin_api_key)],
    summary="Manually trigger a Celery task on demand",
)
async def trigger_task(task_name: str) -> dict:
    if task_name not in _ALLOWED_TASKS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown task '{task_name}'. Allowed: {sorted(_ALLOWED_TASKS)}",
        )
    try:
        from ....packages.revenue_os.celery.celery_app import celery_app
        celery_task_name = f"revenue_os.tasks.{task_name}"
        result = celery_app.send_task(celery_task_name)
        logger.info("Task triggered manually: %s, task_id=%s", task_name, result.id)
        return {"triggered": True, "task_name": task_name, "task_id": result.id}
    except Exception as exc:
        logger.error("Failed to trigger task %s: %s", task_name, exc)
        raise HTTPException(
            status_code=503,
            detail=f"Failed to enqueue task: {exc}",
        )


@router.get(
    "/schedule",
    dependencies=[Depends(require_admin_api_key)],
    summary="View the current Celery beat schedule",
)
async def get_schedule() -> dict:
    from ....packages.revenue_os.celery.celery_app import celery_app
    return {
        name: {
            "task": entry.get("task"),
            "schedule": str(entry.get("schedule")),
            "queue": entry.get("options", {}).get("queue", "default"),
        }
        for name, entry in (celery_app.conf.beat_schedule or {}).items()
    }

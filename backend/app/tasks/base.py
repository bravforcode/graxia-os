"""Shared helpers for managed Celery task execution."""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from functools import wraps
from typing import Any
from uuid import UUID

from app.config import settings
from app.core.control_plane import create_run, mark_run_completed, mark_run_failed, mark_run_started
from app.core.monitoring import metrics_collector
from app.tasks.async_runner import run_async
from app.tasks.dlq_handler import record_dlq_failure
from app.tasks.queues import get_sync_redis_client
from app.tasks.requirements import missing_settings

logger = logging.getLogger(__name__)

_memory_task_locks: dict[str, float] = {}


def _acquire_task_lock(lock_key: str, ttl: int) -> bool:
    redis_client = get_sync_redis_client()
    if redis_client is not None:
        return bool(redis_client.set(lock_key, "1", ex=ttl, nx=True))
    now = datetime.now(UTC).timestamp()
    expires_at = _memory_task_locks.get(lock_key, 0)
    if expires_at > now:
        return False
    _memory_task_locks[lock_key] = now + ttl
    return True


def _release_task_lock(lock_key: str) -> None:
    redis_client = get_sync_redis_client()
    if redis_client is not None:
        redis_client.delete(lock_key)
        return
    _memory_task_locks.pop(lock_key, None)


def idempotent_task(lock_key_template: str, lock_ttl: int = 3600):
    """Prevent duplicate scheduled task execution across workers."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = lock_key_template.format(
                task_name=getattr(func, "__name__", "task"),
                date=datetime.now(UTC).strftime("%Y-%m-%d"),
                **kwargs,
            )
            lock_key = f"task_lock:{key}"
            if not _acquire_task_lock(lock_key, lock_ttl):
                logger.info("Task %s skipped; lock already held for %s", func.__name__, key)
                return {"status": "skipped", "lock_key": key}
            try:
                return func(*args, **kwargs)
            finally:
                _release_task_lock(lock_key)

        return wrapper

    return decorator


async def _execute_managed_run(
    task_name: str,
    queue: str,
    coroutine_factory: Callable[[], Awaitable[Any]],
    trigger_source: str,
    organization_id: UUID | None = None,
) -> Any:
    missing = missing_settings(task_name)
    if missing:
        logger.warning("Task %s skipped: missing config %s", task_name, ", ".join(missing))
        return {"status": "skipped", "reason": "missing_config", "missing": missing}
    tenant_id = organization_id or getattr(settings, "LEGACY_ORGANIZATION_ID", UUID("00000000-0000-0000-0000-000000000001"))
    run = await create_run(
        name=task_name.replace(".", " ").title(),
        task_type=task_name,
        trigger_source=trigger_source,
        context={"queue": queue},
        idempotency_key=f"{task_name}:{datetime.now(UTC).strftime('%Y-%m-%dT%H:%M')}",
        organization_id=tenant_id,
    )
    try:
        await mark_run_started(run.id)
        result = await coroutine_factory()
        normalized = result if isinstance(result, dict) else {"result": result}
        await mark_run_completed(run.id, result=normalized)
        return result
    except Exception as exc:
        await mark_run_failed(run.id, str(exc))
        raise


def execute_managed_async_task(
    *,
    task_name: str,
    queue: str,
    coroutine_factory: Callable[[], Awaitable[Any]],
    trigger_source: str = "scheduler",
    organization_id: UUID | None = None,
) -> Any:
    try:
        result = run_async(_execute_managed_run(task_name, queue, coroutine_factory, trigger_source, organization_id=organization_id))
    except Exception as exc:
        record_dlq_failure(
            task_name=task_name,
            args=(),
            kwargs={},
            exception=exc,
            traceback_text="managed async task failure",
            original_queue=queue,
        )
        metrics_collector.record_agent_execution(task_name, "failed", 0.0)
        raise
    metrics_collector.record_agent_execution(task_name, "success", 0.0)
    return result

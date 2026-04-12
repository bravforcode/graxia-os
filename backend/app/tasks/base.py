"""Shared helpers for managed Celery task execution."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from functools import wraps
from typing import Any

from app.core.control_plane import create_run, mark_run_completed, mark_run_failed, mark_run_started
from app.core.monitoring import metrics_collector
from app.tasks.dlq_handler import record_dlq_failure
from app.tasks.queues import get_sync_redis_client

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


def execute_managed_async_task(
    *,
    task_name: str,
    queue: str,
    coroutine_factory: Callable[[], Awaitable[Any]],
    trigger_source: str = "scheduler",
) -> Any:
    run = asyncio.run(
        create_run(
            name=task_name.replace(".", " ").title(),
            task_type=task_name,
            trigger_source=trigger_source,
            context={"queue": queue},
            idempotency_key=f"{task_name}:{datetime.now(UTC).strftime('%Y-%m-%dT%H:%M')}",
        )
    )
    try:
        asyncio.run(mark_run_started(run.id))
        result = asyncio.run(coroutine_factory())
        normalized = result if isinstance(result, dict) else {"result": result}
        asyncio.run(mark_run_completed(run.id, result=normalized))
        metrics_collector.record_agent_execution(task_name, "success", 0.0)
        return result
    except Exception as exc:
        asyncio.run(mark_run_failed(run.id, str(exc)))
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

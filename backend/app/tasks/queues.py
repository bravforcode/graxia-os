"""Celery queue configuration and broker helpers."""
from __future__ import annotations

from typing import Any

from kombu import Queue

from app.config import settings

CRITICAL_QUEUE = "critical"
DEFAULT_QUEUE = "default"
BACKGROUND_QUEUE = "background"
DLQ_QUEUE = "dlq"

ALL_QUEUES = (
    Queue(CRITICAL_QUEUE, routing_key=CRITICAL_QUEUE, queue_arguments={"x-max-priority": 10}),
    Queue(DEFAULT_QUEUE, routing_key=DEFAULT_QUEUE, queue_arguments={"x-max-priority": 5}),
    Queue(BACKGROUND_QUEUE, routing_key=BACKGROUND_QUEUE, queue_arguments={"x-max-priority": 1}),
    Queue(DLQ_QUEUE, routing_key=DLQ_QUEUE),
)

TASK_ROUTES: dict[str, dict[str, str]] = {
    "tasks.daily_scan.run": {"queue": DEFAULT_QUEUE, "routing_key": DEFAULT_QUEUE},
    "tasks.morning_briefing.run": {"queue": DEFAULT_QUEUE, "routing_key": DEFAULT_QUEUE},
    "tasks.follow_up_check.run": {"queue": DEFAULT_QUEUE, "routing_key": DEFAULT_QUEUE},
    "tasks.job_discovery.run": {"queue": DEFAULT_QUEUE, "routing_key": DEFAULT_QUEUE},
    "tasks.email_processing.run": {"queue": BACKGROUND_QUEUE, "routing_key": BACKGROUND_QUEUE},
    "tasks.weekly_review.run": {"queue": DEFAULT_QUEUE, "routing_key": DEFAULT_QUEUE},
    "tasks.maintenance.weekly_strategy": {"queue": DEFAULT_QUEUE, "routing_key": DEFAULT_QUEUE},
    "tasks.maintenance.identity_snapshot": {"queue": DEFAULT_QUEUE, "routing_key": DEFAULT_QUEUE},
    "tasks.maintenance.obsidian_daily_note": {"queue": BACKGROUND_QUEUE, "routing_key": BACKGROUND_QUEUE},
    "tasks.maintenance.obsidian_refresh": {"queue": BACKGROUND_QUEUE, "routing_key": BACKGROUND_QUEUE},
    "tasks.maintenance.check_dlq_depth": {"queue": CRITICAL_QUEUE, "routing_key": CRITICAL_QUEUE},
    "tasks.backup.run_daily_backup": {"queue": CRITICAL_QUEUE, "routing_key": CRITICAL_QUEUE},
    "tasks.backup.run_restore_drill": {"queue": CRITICAL_QUEUE, "routing_key": CRITICAL_QUEUE},
    "tasks.backup.run_redis_backup": {"queue": BACKGROUND_QUEUE, "routing_key": BACKGROUND_QUEUE},
}


def get_sync_redis_client() -> Any | None:
    try:
        import redis

        client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        client.ping()
        return client
    except Exception:
        return None


async def get_queue_depths(redis_client: Any | None = None) -> dict[str, int]:
    client = redis_client
    if client is None:
        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            await client.ping()
        except Exception:
            return {queue.name: 0 for queue in ALL_QUEUES}

    depths: dict[str, int] = {}
    for queue in ALL_QUEUES:
        try:
            depths[queue.name] = int(await client.llen(queue.name) or 0)
        except Exception:
            depths[queue.name] = 0
    return depths


def get_queue_depths_sync(redis_client: Any | None = None) -> dict[str, int]:
    client = redis_client or get_sync_redis_client()
    if client is None:
        return {queue.name: 0 for queue in ALL_QUEUES}
    depths: dict[str, int] = {}
    for queue in ALL_QUEUES:
        try:
            depths[queue.name] = int(client.llen(queue.name) or 0)
        except Exception:
            depths[queue.name] = 0
    return depths

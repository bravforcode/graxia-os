"""Celery entrypoint for the consolidated Content Ops runtime."""

from __future__ import annotations

from typing import Any

from app.content_ops.contracts import PublishRequest
from app.content_ops.service import execute_publish
from app.database import AsyncSessionLocal
from app.tasks.base import execute_managed_async_task
from app.tasks.celery_app import celery_app
from app.tasks.queues import DEFAULT_QUEUE


async def _publish(payload: dict[str, Any]) -> dict[str, Any]:
    request = PublishRequest.model_validate(payload)
    async with AsyncSessionLocal() as db:
        receipt = await execute_publish(db, request)
        return receipt.model_dump(mode="json")


@celery_app.task(
    name="tasks.content_ops.publish",
    queue=DEFAULT_QUEUE,
    autoretry_for=(),
)
def publish_content_task(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist one publish intent; default worker mode cannot call providers."""

    return execute_managed_async_task(
        task_name="content_ops.publish",
        queue=DEFAULT_QUEUE,
        coroutine_factory=lambda: _publish(payload),
        trigger_source="celery",
    )


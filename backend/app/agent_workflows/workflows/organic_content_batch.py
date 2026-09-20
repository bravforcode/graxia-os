"""Celery boundary for organic content batch processing."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.content_batch import ContentBatch
from app.services.content_batch_service import process_content_batch
from app.tasks.base import execute_managed_async_task
from app.tasks.celery_app import celery_app
from app.tasks.queues import BACKGROUND_QUEUE


CONTENT_BATCH_TASK_NAME = "tasks.organic_content_batch.process"
WEEKLY_CONTENT_TASK_NAME = "tasks.organic_content_batch.schedule_weekly"
logger = logging.getLogger("graxia.tasks.organic_content_batch")


def enqueue_content_batch(batch_id: str) -> str | None:
    """Queue work after the API transaction; return only a task identifier."""

    try:
        result = celery_app.send_task(
            CONTENT_BATCH_TASK_NAME,
            args=[batch_id],
            queue=BACKGROUND_QUEUE,
        )
    except Exception:
        # The batch remains queued and can be replayed by the parent scheduler.
        return None
    return getattr(result, "id", None)


def _weekly_configuration() -> tuple[UUID, str, str] | None:
    """Return explicit weekly config, or None for a safe no-op."""

    if not settings.CONTENT_BATCH_ENABLED:
        return None
    if os.getenv("ORGANIC_CONTENT_WEEKLY_ENABLED", "false").lower() != "true":
        return None
    organization_id = os.getenv("ORGANIC_CONTENT_WEEKLY_ORGANIZATION_ID", "").strip()
    topic = os.getenv("ORGANIC_CONTENT_WEEKLY_TOPIC", "").strip()
    canonical_url = os.getenv("ORGANIC_CONTENT_WEEKLY_CANONICAL_URL", "").strip()
    if not organization_id or not topic or not canonical_url:
        return None
    try:
        return UUID(organization_id), topic, canonical_url
    except ValueError:
        return None


async def _schedule_weekly_content_batch(now: datetime | None = None) -> dict[str, Any]:
    configured = _weekly_configuration()
    if configured is None:
        return {"status": "skipped", "reason": "not_configured"}

    organization_id, topic, canonical_url = configured
    current = now or datetime.now(UTC)
    iso = current.isocalendar()
    idempotency_key = f"organic-weekly:{organization_id}:{iso.year}-W{iso.week:02d}"
    async with AsyncSessionLocal() as db:
        existing = await db.scalar(
            select(ContentBatch).where(
                ContentBatch.organization_id == organization_id,
                ContentBatch.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            return {"status": "existing", "batch_id": str(existing.id)}

        batch = ContentBatch(
            organization_id=organization_id,
            idempotency_key=idempotency_key,
            topic=topic,
            site=os.getenv("ORGANIC_CONTENT_WEEKLY_SITE", "site_a"),
            language=os.getenv("ORGANIC_CONTENT_WEEKLY_LANGUAGE", "en"),
            canonical_url=canonical_url,
            provider="organic",
            status="queued",
            item_count=9,
            live=False,
            dry_run=True,
            queued_at=current,
            utm_source="organic",
            utm_medium="content",
            utm_campaign=f"weekly-{iso.year}-w{iso.week:02d}",
        )
        db.add(batch)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            existing = await db.scalar(
                select(ContentBatch).where(
                    ContentBatch.organization_id == organization_id,
                    ContentBatch.idempotency_key == idempotency_key,
                )
            )
            return {"status": "existing", "batch_id": str(existing.id)} if existing else {
                "status": "failed", "reason": "idempotency_conflict"
            }

        queue_id = enqueue_content_batch(str(batch.id))
        if not queue_id:
            logger.warning("weekly_content_batch_queue_unavailable", extra={"status": "queued"})
        return {"status": "queued", "batch_id": str(batch.id), "queue_id": queue_id}


@celery_app.task(name=WEEKLY_CONTENT_TASK_NAME, queue=BACKGROUND_QUEUE, autoretry_for=())
def schedule_weekly_content_batch() -> dict[str, Any]:
    """Create at most one dry-run 9-item batch per ISO week; never calls AI inline."""

    return asyncio.run(_schedule_weekly_content_batch())


async def _process(batch_id: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        result = await process_content_batch(db, batch_id)
        return result.to_schema().model_dump(mode="json")


@celery_app.task(
    name=CONTENT_BATCH_TASK_NAME,
    queue=BACKGROUND_QUEUE,
    autoretry_for=(),
)
def process_content_batch_task(batch_id: str) -> dict[str, Any]:
    """Worker entrypoint; all generation and publishing stays out of the API."""

    return execute_managed_async_task(
        task_name="organic_content_batch.process",
        queue=BACKGROUND_QUEUE,
        coroutine_factory=lambda: _process(batch_id),
        trigger_source="celery",
    )

"""Tenant-protected queue endpoint for organic content batches."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.auth.dependencies import require_permission
from app.config import settings
from app.database import get_db
from app.models.content_batch import ContentBatch
from app.schemas.content_batch import (
    ContentBatchCreate,
    ContentBatchOut,
    ContentBatchQueued,
)
from app.tasks.celery_app import celery_app
from app.tasks.queues import BACKGROUND_QUEUE


router = APIRouter(prefix="/content-batches", tags=["content-batches"])
DbSession = Annotated[AsyncSession, Depends(get_db)]
CONTENT_BATCH_TASK_NAME = "tasks.organic_content_batch.process"


def enqueue_content_batch(batch_id: str) -> str | None:
    """Queue work without importing the wider workflow package at API startup."""

    try:
        result = celery_app.send_task(
            CONTENT_BATCH_TASK_NAME,
            args=[batch_id],
            queue=BACKGROUND_QUEUE,
        )
    except Exception:
        return None
    return getattr(result, "id", None)


@router.post("", response_model=ContentBatchQueued, status_code=status.HTTP_202_ACCEPTED)
async def create_content_batch(
    payload: ContentBatchCreate,
    db: DbSession,
    auth: AuthContext = Depends(require_permission("runtime:write")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ContentBatchQueued:
    """Persist and queue a batch; content generation happens only in a worker."""

    if auth.organization_id is None:
        raise HTTPException(status_code=401, detail="Organization context required")
    if not settings.CONTENT_BATCH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Content batch engine is temporarily disabled",
        )

    request_key = (idempotency_key or payload.idempotency_key).strip()
    if not request_key:
        raise HTTPException(status_code=422, detail="Idempotency-Key must not be blank")

    existing = await db.scalar(
        select(ContentBatch).where(
            ContentBatch.organization_id == auth.organization_id,
            ContentBatch.idempotency_key == request_key,
        )
    )
    if existing is not None:
        if existing.status == "failed":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Content batch queueing previously failed",
            )
        return ContentBatchQueued(
            id=existing.id,
            status=existing.status,
            item_count=existing.item_count,
            queue_id=None,
            idempotency_key=existing.idempotency_key,
            created_at=existing.created_at,
        )

    batch = ContentBatch(
        organization_id=auth.organization_id,
        idempotency_key=request_key,
        topic=payload.topic,
        site=payload.site,
        language=payload.language,
        canonical_url=payload.canonical_url,
        provider=payload.provider,
        approval_id=payload.approval_id,
        # These gates are server-derived from approval/runtime state by the worker.
        claim_reviewed=False,
        claim_ids=[],
        canary_passed=False,
        provider_consent=False,
        provider_credentials_available=False,
        utm_source=payload.utm_source,
        utm_medium=payload.utm_medium,
        utm_campaign=payload.utm_campaign,
        live=payload.live,
        dry_run=payload.dry_run and not payload.live,
        item_count=9,
        queued_at=datetime.now(UTC),
    )
    db.add(batch)
    try:
        await db.commit()
        await db.refresh(batch)
    except IntegrityError:
        await db.rollback()
        existing = await db.scalar(
            select(ContentBatch).where(
                ContentBatch.organization_id == auth.organization_id,
                ContentBatch.idempotency_key == request_key,
            )
        )
        if existing is None:
            raise
        return ContentBatchQueued(
            id=existing.id,
            status=existing.status,
            item_count=existing.item_count,
            queue_id=None,
            idempotency_key=existing.idempotency_key,
            created_at=existing.created_at,
        )

    queue_id = enqueue_content_batch(str(batch.id))
    if not queue_id:
        batch.status = "failed"
        batch.error_message = "Content batch could not be queued"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Content batch could not be queued",
        )
    return ContentBatchQueued(
        id=batch.id,
        status=batch.status,
        item_count=batch.item_count,
        queue_id=queue_id,
        idempotency_key=batch.idempotency_key,
        created_at=batch.created_at,
    )


@router.get("", response_model=list[ContentBatchOut])
async def list_content_batches(
    db: DbSession,
    auth: AuthContext = Depends(require_permission("runtime:read")),
):
    if auth.organization_id is None:
        raise HTTPException(status_code=401, detail="Organization context required")
    result = await db.execute(
        select(ContentBatch)
        .where(ContentBatch.organization_id == auth.organization_id)
        .order_by(ContentBatch.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{batch_id}", response_model=ContentBatchOut)
async def get_content_batch(
    batch_id: str,
    db: DbSession,
    auth: AuthContext = Depends(require_permission("runtime:read")),
):
    if auth.organization_id is None:
        raise HTTPException(status_code=401, detail="Organization context required")
    batch = await db.scalar(
        select(ContentBatch).where(
            ContentBatch.id == batch_id,
            ContentBatch.organization_id == auth.organization_id,
        )
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="Content batch not found")
    return batch


@router.get("/{batch_id}/export")
async def export_content_batch(
    batch_id: str,
    db: DbSession,
    auth: AuthContext = Depends(require_permission("runtime:read")),
):
    if auth.organization_id is None:
        raise HTTPException(status_code=401, detail="Organization context required")
    batch = await db.scalar(
        select(ContentBatch).where(
            ContentBatch.id == batch_id,
            ContentBatch.organization_id == auth.organization_id,
        )
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="Content batch not found")
    return {
        "batch_id": str(batch.id),
        "status": batch.status,
        "evidence_state": "dry_run" if batch.status == "exported" else "pending",
        "manifest": batch.export_manifest or {},
        "items": [
            {
                "item_key": item.item_key,
                "channel": item.channel,
                "title": item.title,
                "body": item.body,
                "canonical_url": item.canonical_url,
                "utm_params": item.utm_params or {},
                "status": item.status,
            }
            for item in batch.items
        ],
    }


@router.post("/{batch_id}/publish", response_model=ContentBatchQueued, status_code=status.HTTP_202_ACCEPTED)
async def publish_content_batch(
    batch_id: str,
    db: DbSession,
    auth: AuthContext = Depends(require_permission("runtime:write")),
):
    """Request a live attempt; the worker re-evaluates every server-side gate."""
    if auth.organization_id is None:
        raise HTTPException(status_code=401, detail="Organization context required")
    batch = await db.scalar(
        select(ContentBatch).where(
            ContentBatch.id == batch_id,
            ContentBatch.organization_id == auth.organization_id,
        )
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="Content batch not found")
    batch.live = True
    batch.dry_run = False
    batch.status = "queued"
    await db.commit()
    queue_id = enqueue_content_batch(str(batch.id))
    if not queue_id:
        batch.status = "failed"
        batch.error_message = "Content batch could not be queued"
        await db.commit()
        raise HTTPException(status_code=503, detail="Content batch could not be queued")
    return ContentBatchQueued(
        id=batch.id,
        status=batch.status,
        item_count=batch.item_count,
        queue_id=queue_id,
        idempotency_key=batch.idempotency_key,
        created_at=batch.created_at,
    )

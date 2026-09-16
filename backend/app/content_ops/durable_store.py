"""Async SQLAlchemy persistence for redacted Content Ops publish attempts."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.publish_attempt import PublishAttempt

from .contracts import PublishReceipt, PublishRequest


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite's timezone-naive round-trip for deterministic tests."""

    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _attempt_uuid(attempt_id: str) -> UUID:
    """Keep the public receipt ID stable when it is round-tripped through SQL."""

    try:
        return UUID(attempt_id.removeprefix("attempt-"))
    except (ValueError, AttributeError):
        return uuid4()


class SQLAlchemyPublishAttemptStore:
    """Durable idempotency store; callers own the session transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _find(self, key: tuple[str, str, str]) -> PublishAttempt | None:
        tenant_id, provider, idempotency_key = key
        result = await self.session.execute(
            select(PublishAttempt).where(
                PublishAttempt.tenant_id == tenant_id,
                PublishAttempt.provider == provider,
                PublishAttempt.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()

    async def get_async(self, key: tuple[str, str, str]) -> PublishReceipt | None:
        row = await self._find(key)
        if row is None:
            return None
        return PublishReceipt(
            attempt_id=f"attempt-{row.id}",
            provider_status=row.provider_status,
            external_id=row.external_id,
            started_at=_as_utc(row.started_at),
            finished_at=_as_utc(row.finished_at),
            retryable=row.retryable,
            redacted_error_code=row.redacted_error_code,
        )

    async def put_async(
        self,
        key: tuple[str, str, str],
        request: PublishRequest,
        receipt: PublishReceipt,
    ) -> None:
        """Insert once; a concurrent duplicate becomes a harmless replay."""

        tenant_id, provider, idempotency_key = key
        row = PublishAttempt(
            id=_attempt_uuid(receipt.attempt_id),
            tenant_id=tenant_id,
            content_id=request.content_id,
            provider=provider,
            approval_id=request.approval_id,
            idempotency_key=idempotency_key,
            scheduled_at=request.scheduled_at,
            dry_run=request.dry_run,
            live=request.live,
            provider_status=receipt.provider_status,
            external_id=receipt.external_id,
            started_at=receipt.started_at,
            finished_at=receipt.finished_at,
            retryable=receipt.retryable,
            redacted_error_code=receipt.redacted_error_code,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(row)
                await self.session.flush()
        except IntegrityError:
            # The unique constraint is the final idempotency arbiter. A
            # concurrent writer already stored the same key; leave its
            # receipt authoritative and keep the caller's transaction usable.
            return

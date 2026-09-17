"""Async SQLAlchemy persistence for redacted Content Ops publish attempts."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.publish_attempt import PublishAttempt

from .contracts import PublishReceipt, PublishRequest


DEFAULT_CLAIM_TTL = timedelta(minutes=5)
_IN_PROGRESS_STATUS = "in_progress"
_STALE_STATUS = "stale"


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
    """Durable idempotency store with committed claim transactions."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        claim_ttl: timedelta = DEFAULT_CLAIM_TTL,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.session = session
        self.claim_ttl = claim_ttl
        self._clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        return _as_utc(self._clock())

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

    def _receipt_from_row(self, row: PublishAttempt) -> PublishReceipt:
        provider_status = row.provider_status
        error_code = row.redacted_error_code
        retryable = row.retryable
        if provider_status == _IN_PROGRESS_STATUS:
            expires_at = row.claim_expires_at
            if expires_at is not None and self._now() >= _as_utc(expires_at):
                provider_status = _STALE_STATUS
                error_code = "PUBLISH_STALE"
            else:
                error_code = "PUBLISH_IN_PROGRESS"
            retryable = False

        return PublishReceipt(
            attempt_id=f"attempt-{row.id}",
            provider_status=provider_status,
            external_id=row.external_id,
            started_at=_as_utc(row.started_at),
            finished_at=_as_utc(row.finished_at),
            retryable=retryable,
            redacted_error_code=error_code,
        )

    async def claim_async(
        self,
        key: tuple[str, str, str],
        request: PublishRequest,
    ) -> PublishReceipt | None:
        """Insert a durable claim before a provider call.

        The unique key arbitrates concurrent inserts. The claim transaction is
        committed before the caller is allowed to invoke the provider.
        """

        existing = await self._find(key)
        if existing is not None:
            return self._receipt_from_row(existing)

        tenant_id, provider, idempotency_key = key
        now = self._now()
        row = PublishAttempt(
            id=uuid4(),
            tenant_id=tenant_id,
            content_id=request.content_id,
            provider=provider,
            approval_id=request.approval_id,
            idempotency_key=idempotency_key,
            scheduled_at=request.scheduled_at,
            dry_run=request.dry_run,
            live=request.live,
            provider_status=_IN_PROGRESS_STATUS,
            started_at=now,
            finished_at=now,
            retryable=False,
            redacted_error_code="PUBLISH_IN_PROGRESS",
            claim_expires_at=now + self.claim_ttl,
        )
        self.session.add(row)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            existing = await self._find(key)
            if existing is None:
                raise
            return self._receipt_from_row(existing)
        return None

    async def complete_async(
        self,
        key: tuple[str, str, str],
        receipt: PublishReceipt,
    ) -> PublishReceipt:
        """Replace the owned claim with its terminal redacted receipt."""

        row = await self._find(key)
        if row is None:
            raise RuntimeError("publish claim missing")
        row.provider_status = receipt.provider_status
        row.external_id = receipt.external_id
        row.finished_at = receipt.finished_at
        row.retryable = receipt.retryable
        row.redacted_error_code = receipt.redacted_error_code
        row.claim_expires_at = None
        completed = self._receipt_from_row(row)
        await self.session.commit()
        return completed

    async def get_async(self, key: tuple[str, str, str]) -> PublishReceipt | None:
        row = await self._find(key)
        if row is None:
            return None
        return self._receipt_from_row(row)

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
            claim_expires_at=None,
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

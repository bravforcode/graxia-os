"""Provider-neutral publishing orchestration for the consolidated Content Ops path.

The orchestrator owns safety gates and idempotency. Provider adapters own only
their provider call and must return a redacted result. Persistence is injected
so the same contract can move from the test store to a durable repository.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from .contracts import PublishReceipt, PublishRequest


class PublishAttemptStore(Protocol):
    def get(self, key: tuple[str, str, str]) -> PublishReceipt | None:
        """Return a prior receipt for a tenant/provider/idempotency key."""

    def put(self, key: tuple[str, str, str], receipt: PublishReceipt) -> None:
        """Persist a redacted receipt before returning it to the caller."""


class AsyncPublishAttemptStore(Protocol):
    """Async persistence seam for the application database."""

    async def get_async(self, key: tuple[str, str, str]) -> PublishReceipt | None:
        """Return a prior durable receipt for an idempotency key."""

    async def put_async(
        self,
        key: tuple[str, str, str],
        request: PublishRequest,
        receipt: PublishReceipt,
    ) -> None:
        """Persist a request and its redacted receipt atomically."""


class PublisherAdapter(Protocol):
    def publish(self, request: PublishRequest) -> "AdapterResult":
        """Perform one provider call only after the orchestrator gates it."""


@dataclass(frozen=True)
class AdapterResult:
    """Already-redacted provider outcome; raw payloads are not accepted."""

    provider_status: str
    external_id: str | None = None
    retryable: bool = False
    error_code: str | None = None


@dataclass
class InMemoryPublishAttemptStore:
    """Deterministic store for tests and local dry-runs; not production storage."""

    _receipts: dict[tuple[str, str, str], PublishReceipt] = field(default_factory=dict)

    def get(self, key: tuple[str, str, str]) -> PublishReceipt | None:
        return self._receipts.get(key)

    def put(self, key: tuple[str, str, str], receipt: PublishReceipt) -> None:
        self._receipts[key] = receipt

    async def get_async(self, key: tuple[str, str, str]) -> PublishReceipt | None:
        return self.get(key)

    async def put_async(
        self,
        key: tuple[str, str, str],
        request: PublishRequest,
        receipt: PublishReceipt,
    ) -> None:
        self.put(key, receipt)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _receipt(
    *,
    status: str,
    retryable: bool = False,
    error_code: str | None = None,
    external_id: str | None = None,
    started_at: datetime,
    finished_at: datetime,
) -> PublishReceipt:
    return PublishReceipt(
        attempt_id=f"attempt-{uuid4()}",
        provider_status=status,
        external_id=external_id,
        started_at=started_at,
        finished_at=finished_at,
        retryable=retryable,
        redacted_error_code=error_code,
    )


class ContentOpsPublisher:
    """Execute a publish intent with explicit, auditable safety gates."""

    def __init__(self, store: PublishAttemptStore | None = None) -> None:
        self.store = store or InMemoryPublishAttemptStore()

    def execute(
        self,
        request: PublishRequest,
        *,
        adapter: PublisherAdapter | None = None,
        approval_granted: bool = False,
        consent_granted: bool = False,
        external_publish_enabled: bool = False,
    ) -> PublishReceipt:
        key = (request.tenant_id, request.provider, request.idempotency_key)
        prior = self.store.get(key)
        if prior is not None:
            return prior

        receipt = self._execute_intent(
            request,
            adapter=adapter,
            approval_granted=approval_granted,
            consent_granted=consent_granted,
            external_publish_enabled=external_publish_enabled,
        )
        self.store.put(key, receipt)
        return receipt

    async def execute_async(
        self,
        request: PublishRequest,
        *,
        adapter: PublisherAdapter | None = None,
        approval_granted: bool = False,
        consent_granted: bool = False,
        external_publish_enabled: bool = False,
    ) -> PublishReceipt:
        """Execute against the injected async store used by web/worker code."""

        get_async = getattr(self.store, "get_async", None)
        put_async = getattr(self.store, "put_async", None)
        if not callable(get_async) or not callable(put_async):
            raise TypeError("async publish execution requires an async attempt store")

        key = (request.tenant_id, request.provider, request.idempotency_key)
        prior = await get_async(key)
        if prior is not None:
            return prior

        receipt = self._execute_intent(
            request,
            adapter=adapter,
            approval_granted=approval_granted,
            consent_granted=consent_granted,
            external_publish_enabled=external_publish_enabled,
        )
        await put_async(key, request, receipt)
        return receipt

    def _execute_intent(
        self,
        request: PublishRequest,
        *,
        adapter: PublisherAdapter | None,
        approval_granted: bool,
        consent_granted: bool,
        external_publish_enabled: bool,
    ) -> PublishReceipt:
        """Apply the safety gates once; callers choose sync or async persistence."""

        started_at = _now()
        if request.dry_run:
            receipt = _receipt(
                status="dry_run",
                started_at=started_at,
                finished_at=_now(),
            )
            return receipt

        if not request.live:
            receipt = _receipt(
                status="blocked",
                error_code="LIVE_FLAG_REQUIRED",
                started_at=started_at,
                finished_at=_now(),
            )
            return receipt

        if not approval_granted:
            receipt = _receipt(
                status="blocked",
                error_code="APPROVAL_REQUIRED",
                started_at=started_at,
                finished_at=_now(),
            )
            return receipt

        if not consent_granted:
            receipt = _receipt(
                status="blocked",
                error_code="CONSENT_REQUIRED",
                started_at=started_at,
                finished_at=_now(),
            )
            return receipt

        if not external_publish_enabled or adapter is None:
            receipt = _receipt(
                status="blocked",
                error_code="PROVIDER_NOT_ENABLED",
                started_at=started_at,
                finished_at=_now(),
            )
            return receipt

        try:
            result = adapter.publish(request)
            if not isinstance(result, AdapterResult):
                raise TypeError("adapter returned an invalid result")
            receipt = _receipt(
                status=result.provider_status,
                external_id=result.external_id,
                retryable=result.retryable,
                error_code=result.error_code,
                started_at=started_at,
                finished_at=_now(),
            )
        except Exception:
            receipt = _receipt(
                status="failed",
                retryable=True,
                error_code="PROVIDER_ERROR",
                started_at=started_at,
                finished_at=_now(),
            )
        return receipt

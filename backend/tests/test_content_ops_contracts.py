from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.content_ops.contracts import ContentLifecycle, PublishReceipt, PublishRequest


def test_publish_request_is_dry_run_by_default():
    request = PublishRequest(
        tenant_id="tenant-1",
        content_id="content-1",
        provider="YouTube",
        approval_id="approval-1",
        idempotency_key="publish-1",
    )

    assert request.provider == "youtube"
    assert request.dry_run is True
    assert request.live is False
    assert ContentLifecycle.APPROVED.value == "approved"


def test_publish_request_rejects_live_dry_run_conflict_and_extra_payload():
    with pytest.raises(ValidationError):
        PublishRequest(
            tenant_id="tenant-1",
            content_id="content-1",
            provider="youtube",
            approval_id="approval-1",
            idempotency_key="publish-1",
            live=True,
        )
    with pytest.raises(ValidationError):
        PublishRequest(
            tenant_id="tenant-1",
            content_id="content-1",
            provider="youtube",
            approval_id="approval-1",
            idempotency_key="publish-1",
            raw_provider_payload={"token": "never"},
        )


def test_publish_receipt_rejects_raw_secret_or_unordered_times():
    start = datetime(2026, 9, 16, tzinfo=timezone.utc)
    with pytest.raises(ValidationError):
        PublishReceipt(
            attempt_id="attempt-1",
            provider_status="sk_live_not-safe",
            started_at=start,
            finished_at=start,
            retryable=False,
        )
    with pytest.raises(ValidationError):
        PublishReceipt(
            attempt_id="attempt-1",
            provider_status="failed",
            started_at=start,
            finished_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
            retryable=True,
            redacted_error_code="timeout",
        )

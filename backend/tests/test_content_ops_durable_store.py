from app.content_ops.durable_store import SQLAlchemyPublishAttemptStore
from app.content_ops.publisher import AdapterResult, ContentOpsPublisher
from app.content_ops.contracts import PublishRequest
from app.models.publish_attempt import PublishAttempt
from sqlalchemy import select


class CountingAdapter:
    def __init__(self):
        self.calls = 0

    def publish(self, request):
        self.calls += 1
        return AdapterResult(provider_status="published", external_id="provider-item-1")


def _request(**overrides):
    values = {
        "tenant_id": "tenant-1",
        "content_id": "content-1",
        "provider": "youtube",
        "approval_id": "approval-1",
        "idempotency_key": "publish-1",
        "live": True,
        "dry_run": False,
    }
    values.update(overrides)
    return PublishRequest(**values)


async def test_sqlalchemy_store_persists_and_replays_idempotently(db_session):
    adapter = CountingAdapter()
    publisher = ContentOpsPublisher(SQLAlchemyPublishAttemptStore(db_session))
    request = _request()

    first = await publisher.execute_async(
        request,
        adapter=adapter,
        approval_granted=True,
        consent_granted=True,
        external_publish_enabled=True,
    )
    await db_session.commit()
    second = await publisher.execute_async(
        request,
        adapter=adapter,
        approval_granted=True,
        consent_granted=True,
        external_publish_enabled=True,
    )

    assert second == first
    assert adapter.calls == 1
    row = await db_session.scalar(select(PublishAttempt))
    assert row is not None
    assert row.tenant_id == "tenant-1"
    assert row.provider_status == "published"
    assert row.external_id == "provider-item-1"


async def test_sqlalchemy_store_keeps_blocked_receipt_redacted(db_session):
    publisher = ContentOpsPublisher(SQLAlchemyPublishAttemptStore(db_session))
    receipt = await publisher.execute_async(_request(), external_publish_enabled=False)
    await db_session.commit()

    assert receipt.provider_status == "blocked"
    assert receipt.redacted_error_code == "APPROVAL_REQUIRED"
    row = await db_session.scalar(select(PublishAttempt))
    assert row is not None
    assert row.redacted_error_code == "APPROVAL_REQUIRED"
    assert not hasattr(row, "provider_payload")

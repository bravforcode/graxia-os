import asyncio
from datetime import UTC, datetime, timedelta

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


async def test_sqlalchemy_claim_blocks_duplicate_before_provider_call(db_session, session_factory):
    claimed = asyncio.Event()
    release = asyncio.Event()

    class PausingStore(SQLAlchemyPublishAttemptStore):
        async def claim_async(self, key, request):
            prior = await super().claim_async(key, request)
            if prior is None:
                claimed.set()
                await release.wait()
            return prior

    adapter = CountingAdapter()
    request = _request()
    publisher = ContentOpsPublisher(PausingStore(db_session))

    async with session_factory() as duplicate_session:
        duplicate_publisher = ContentOpsPublisher(SQLAlchemyPublishAttemptStore(duplicate_session))
        first_task = asyncio.create_task(
            publisher.execute_async(
                request,
                adapter=adapter,
                approval_granted=True,
                consent_granted=True,
                external_publish_enabled=True,
            )
        )
        await claimed.wait()

        duplicate = await duplicate_publisher.execute_async(
            request,
            adapter=adapter,
            approval_granted=True,
            consent_granted=True,
            external_publish_enabled=True,
        )
        assert duplicate.provider_status == "in_progress"
        assert duplicate.redacted_error_code == "PUBLISH_IN_PROGRESS"
        assert adapter.calls == 0

        release.set()
        first = await first_task
        replay = await duplicate_publisher.execute_async(
            request,
            adapter=adapter,
            approval_granted=True,
            consent_granted=True,
            external_publish_enabled=True,
        )

    assert first.provider_status == "published"
    assert replay == first
    assert adapter.calls == 1
    assert "secret" not in duplicate.model_dump_json()


async def test_sqlalchemy_store_reports_stale_claim_without_raw_details(db_session):
    current = [datetime(2026, 1, 1, tzinfo=UTC)]
    store = SQLAlchemyPublishAttemptStore(
        db_session,
        claim_ttl=timedelta(seconds=5),
        clock=lambda: current[0],
    )
    request = _request()
    key = (request.tenant_id, request.provider, request.idempotency_key)

    assert await store.claim_async(key, request) is None
    current[0] += timedelta(seconds=6)

    stale = await store.get_async(key)
    assert stale is not None
    assert stale.provider_status == "stale"
    assert stale.redacted_error_code == "PUBLISH_STALE"
    assert not stale.retryable
    assert "secret" not in stale.model_dump_json()


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

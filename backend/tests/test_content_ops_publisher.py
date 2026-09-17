from app.content_ops.publisher import (
    AdapterResult,
    ContentOpsPublisher,
    InMemoryPublishAttemptStore,
)
from app.content_ops.contracts import PublishRequest


class CountingAdapter:
    def __init__(self, result=None):
        self.calls = 0
        self.result = result or AdapterResult(provider_status="published", external_id="provider-1")

    def publish(self, request):
        self.calls += 1
        return self.result


def request(**overrides):
    values = {
        "tenant_id": "tenant-1",
        "content_id": "content-1",
        "provider": "youtube",
        "approval_id": "approval-1",
        "idempotency_key": "publish-1",
    }
    values.update(overrides)
    return PublishRequest(**values)


def test_dry_run_never_calls_provider():
    adapter = CountingAdapter()
    receipt = ContentOpsPublisher().execute(request(), adapter=adapter)
    assert receipt.provider_status == "dry_run"
    assert adapter.calls == 0


def test_live_requires_approval_consent_and_external_gate():
    adapter = CountingAdapter()
    live = request(live=True, dry_run=False)
    blocked = ContentOpsPublisher().execute(
        live,
        adapter=adapter,
        approval_granted=False,
        consent_granted=True,
        external_publish_enabled=True,
    )
    assert blocked.provider_status == "blocked"
    assert blocked.redacted_error_code == "APPROVAL_REQUIRED"
    assert adapter.calls == 0


def test_live_call_is_idempotent_per_tenant_provider_and_key():
    adapter = CountingAdapter()
    publisher = ContentOpsPublisher(InMemoryPublishAttemptStore())
    live = request(live=True, dry_run=False)
    first = publisher.execute(
        live,
        adapter=adapter,
        approval_granted=True,
        consent_granted=True,
        external_publish_enabled=True,
    )
    second = publisher.execute(
        live,
        adapter=adapter,
        approval_granted=True,
        consent_granted=True,
        external_publish_enabled=True,
    )
    assert first == second
    assert adapter.calls == 1


def test_provider_exception_is_redacted_and_replayable():
    class BrokenAdapter:
        def publish(self, request):
            raise RuntimeError("secret provider payload should never escape")

    publisher = ContentOpsPublisher()
    receipt = publisher.execute(
        request(live=True, dry_run=False),
        adapter=BrokenAdapter(),
        approval_granted=True,
        consent_granted=True,
        external_publish_enabled=True,
    )
    assert receipt.provider_status == "failed"
    assert receipt.redacted_error_code == "PROVIDER_ERROR"
    assert "secret" not in receipt.model_dump_json()

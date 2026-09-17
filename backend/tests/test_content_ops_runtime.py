from app.content_ops.adapters import (
    CallablePublisherAdapter,
    ProviderAdapterRegistry,
    parse_provider_allowlist,
)
from app.content_ops.contracts import PublishRequest
from app.content_ops.publisher import AdapterResult
from app.content_ops.service import PublishRuntimePolicy, execute_publish
from app.models.publish_attempt import PublishAttempt
from sqlalchemy import select


def _request(**overrides) -> PublishRequest:
    values = {
        "tenant_id": "tenant-runtime",
        "content_id": "content-1",
        "provider": "youtube",
        "approval_id": "approval-1",
        "idempotency_key": "runtime-1",
    }
    values.update(overrides)
    return PublishRequest(**values)


def test_registry_normalizes_allowlist_and_injects_adapter():
    calls = []
    adapter = CallablePublisherAdapter(
        "YouTube",
        lambda request: calls.append(request.content_id)
        or AdapterResult(provider_status="published", external_id="item-1"),
    )
    registry = ProviderAdapterRegistry({"YOUTUBE": adapter})

    assert registry.providers == ("youtube",)
    assert registry.resolve("youtube") is adapter
    assert parse_provider_allowlist(" youtube, instagram, ") == {"youtube", "instagram"}


async def test_service_default_is_dry_run_and_durable(db_session):
    receipt = await execute_publish(db_session, _request())
    await db_session.commit()

    assert receipt.provider_status == "dry_run"
    row = await db_session.scalar(select(PublishAttempt))
    assert row is not None
    assert row.provider_status == "dry_run"


async def test_service_requires_explicit_policy_before_adapter_call(db_session):
    calls = []
    adapter = CallablePublisherAdapter(
        "youtube",
        lambda request: calls.append(request.content_id)
        or AdapterResult(provider_status="published", external_id="item-2"),
    )
    request = _request(live=True, dry_run=False)
    registry = ProviderAdapterRegistry({"youtube": adapter})

    blocked = await execute_publish(
        db_session,
        request,
        approval_granted=True,
        consent_granted=True,
        registry=registry,
        policy=PublishRuntimePolicy(
            external_publish_enabled=True,
            allowed_providers=frozenset(),
        ),
    )
    assert blocked.provider_status == "blocked"
    assert blocked.redacted_error_code == "PROVIDER_NOT_ENABLED"
    assert calls == []

    allowed = await execute_publish(
        db_session,
        _request(idempotency_key="runtime-2"),
        registry=registry,
        policy=PublishRuntimePolicy(
            external_publish_enabled=True,
            allowed_providers=frozenset({"youtube"}),
        ),
    )
    assert allowed.provider_status == "dry_run"
    assert calls == []

    live = await execute_publish(
        db_session,
        _request(idempotency_key="runtime-3", live=True, dry_run=False),
        approval_granted=True,
        consent_granted=True,
        registry=registry,
        policy=PublishRuntimePolicy(
            external_publish_enabled=True,
            allowed_providers=frozenset({"youtube"}),
        ),
    )
    assert live.provider_status == "published"
    assert calls == ["content-1"]


async def test_api_uses_authenticated_tenant_and_defaults_to_dry_run(async_client):
    response = await async_client.post(
        "/api/v1/content-ops/publish",
        json={
            "content_id": "content-api-1",
            "provider": "youtube",
            "approval_id": "approval-api-1",
            "idempotency_key": "api-runtime-1",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["provider_status"] == "dry_run"

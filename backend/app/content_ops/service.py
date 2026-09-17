"""Application service joining Content Ops safety, adapters, and durable storage."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

from .adapters import ProviderAdapterRegistry, empty_provider_registry, parse_provider_allowlist
from .contracts import PublishReceipt, PublishRequest
from .durable_store import SQLAlchemyPublishAttemptStore
from .publisher import ContentOpsPublisher


@dataclass(frozen=True)
class PublishRuntimePolicy:
    """Runtime gates; all external publishing is disabled by default."""

    external_publish_enabled: bool = False
    allowed_providers: frozenset[str] = frozenset()


def configured_runtime_policy() -> PublishRuntimePolicy:
    """Read only the explicit, fail-closed provider runtime settings."""

    return PublishRuntimePolicy(
        external_publish_enabled=bool(settings.CONTENT_OPS_EXTERNAL_PUBLISH_ENABLED),
        allowed_providers=parse_provider_allowlist(settings.CONTENT_OPS_PROVIDER_ALLOWLIST),
    )


async def execute_publish(
    db: AsyncSession,
    request: PublishRequest,
    *,
    approval_granted: bool = False,
    consent_granted: bool = False,
    registry: ProviderAdapterRegistry | None = None,
    policy: PublishRuntimePolicy | None = None,
) -> PublishReceipt:
    """Execute one idempotent publish intent through the canonical runtime.

    No provider is available unless a caller injects an adapter and the
    explicit runtime policy enables that provider.  The default path is safe
    for API requests, workers, local development, and CI.
    """

    runtime_policy = policy or configured_runtime_policy()
    provider_registry = registry or empty_provider_registry()
    adapter = provider_registry.resolve(request.provider)
    provider_enabled = (
        runtime_policy.external_publish_enabled
        and request.provider in runtime_policy.allowed_providers
        and adapter is not None
    )
    publisher = ContentOpsPublisher(SQLAlchemyPublishAttemptStore(db))
    return await publisher.execute_async(
        request,
        adapter=adapter,
        approval_granted=approval_granted,
        consent_granted=consent_granted,
        external_publish_enabled=provider_enabled,
    )


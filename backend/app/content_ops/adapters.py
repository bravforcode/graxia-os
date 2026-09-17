"""Provider adapter registry for the consolidated Content Ops runtime.

The registry is deliberately dependency-injected.  It gives the API and Celery
worker one stable seam without importing Auto-Post provider clients or making
network calls during application startup.  Production adapters can be added
only by explicit configuration and tests can use a deterministic callback.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from .contracts import PublishRequest
from .publisher import AdapterResult, PublisherAdapter

_PROVIDER_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{1,31}$")


def normalize_provider_name(value: str) -> str:
    """Return a safe canonical provider name or reject ambiguous input."""

    provider = value.strip().lower()
    if not _PROVIDER_NAME.fullmatch(provider):
        raise ValueError("provider must be a safe provider name")
    return provider


@dataclass(frozen=True)
class CallablePublisherAdapter:
    """Adapter seam for a provider client owned by a separate integration.

    The callback must return an already-redacted :class:`AdapterResult`.  Raw
    provider exceptions are still caught by ``ContentOpsPublisher``.
    """

    provider: str
    callback: Callable[[PublishRequest], AdapterResult]

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", normalize_provider_name(self.provider))

    def publish(self, request: PublishRequest) -> AdapterResult:
        if request.provider != self.provider:
            raise ValueError("provider adapter mismatch")
        result = self.callback(request)
        if not isinstance(result, AdapterResult):
            raise TypeError("provider callback must return AdapterResult")
        return result


class ProviderAdapterRegistry:
    """Immutable-at-the-boundary registry for explicit provider adapters."""

    def __init__(self, adapters: Mapping[str, PublisherAdapter] | None = None) -> None:
        self._adapters: dict[str, PublisherAdapter] = {}
        for provider, adapter in (adapters or {}).items():
            self.register(provider, adapter)

    def register(self, provider: str, adapter: PublisherAdapter) -> None:
        """Register one adapter; duplicate provider registrations replace safely."""

        self._adapters[normalize_provider_name(provider)] = adapter

    def resolve(self, provider: str) -> PublisherAdapter | None:
        return self._adapters.get(normalize_provider_name(provider))

    @property
    def providers(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))


def parse_provider_allowlist(raw: str | None) -> frozenset[str]:
    """Parse a comma-separated allowlist, ignoring empty values."""

    if not raw:
        return frozenset()
    return frozenset(normalize_provider_name(item) for item in raw.split(",") if item.strip())


def empty_provider_registry() -> ProviderAdapterRegistry:
    """Return the safe default: no external provider is configured."""

    return ProviderAdapterRegistry()


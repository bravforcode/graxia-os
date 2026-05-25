"""AuthContext — organization-scoped authentication context for Graxia OS."""
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


LOCAL_DEV_ORGANIZATION_ID = UUID("00000000-0000-0000-0000-000000000001")
"""Default local-dev org ID. Never use in staging or production."""


@dataclass(frozen=True)
class AuthContext:
    """Organization-scoped authentication context.

    Carried through the request lifecycle to enforce tenancy.
    """

    actor_type: str = "user"
    """One of: 'system' | 'user' | 'agent' | 'service'."""

    actor_id: str | None = None
    """Identity of the actor (user ID, agent name, etc.)."""

    organization_id: UUID = LOCAL_DEV_ORGANIZATION_ID
    """Scoped organization — every operation uses this."""

    permissions: list[str] = field(default_factory=list)
    """List of permission strings for fine-grained access control."""

    request_id: str | None = None
    """Correlation ID for the request."""

    environment: str = "local"
    """One of: 'local' | 'test' | 'staging' | 'production'."""

    is_mock_auth: bool = True
    """True when using local-dev mock auth (no real JWT / org headers)."""

    @property
    def is_system(self) -> bool:
        return self.actor_type == "system"

    @property
    def is_staging_or_production(self) -> bool:
        return self.environment in ("staging", "production")

    @property
    def has_organization(self) -> bool:
        return self.organization_id is not None


# Convenience constant for local development
LocalDevAuthContext = AuthContext(
    actor_type="system",
    actor_id="local-dev",
    organization_id=LOCAL_DEV_ORGANIZATION_ID,
    environment="local",
    is_mock_auth=True,
)

"""AuthContext — organization-scoped authentication context for Graxia OS."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


LOCAL_DEV_ORGANIZATION_ID = UUID("00000000-0000-0000-0000-000000000001")
"""Default local-dev org ID. Never use in staging or production."""


@dataclass(frozen=True)
class AuthContext:
    """Organization-scoped authentication context.

    Carried through the request lifecycle to enforce tenancy.
    """

    actor_type: str = "user"
    """One of: 'anonymous' | 'customer' | 'user' | 'admin' | 'agent' | 'service' | 'system'."""

    actor_id: str | None = None
    """Identity of the actor (user ID, agent name, etc.)."""

    organization_id: UUID | None = LOCAL_DEV_ORGANIZATION_ID
    """Scoped organization — every operation uses this."""

    permissions: list[str] = field(default_factory=list)
    """List of permission strings for fine-grained access control."""

    scopes: list[str] = field(default_factory=list)
    """Optional auth scopes from bearer/API-key/service auth."""

    request_id: str | None = None
    """Stable request ID for this request."""

    correlation_id: str | None = None
    """Cross-service correlation ID."""

    environment: str = "local"
    """One of: 'local' | 'test' | 'staging' | 'production'."""

    auth_method: str = "local_test"
    """One of: 'none' | 'local_test' | 'bearer_jwt' | 'api_key' | 'internal_service' | 'customer_token'."""

    is_mock_auth: bool = True
    """True when using local-dev mock auth (no real JWT / org headers)."""

    is_authenticated: bool = False
    is_internal: bool = False
    is_customer: bool = False
    issued_at: datetime | None = None
    expires_at: datetime | None = None

    @property
    def is_system(self) -> bool:
        return self.actor_type == "system"

    @property
    def is_staging_or_production(self) -> bool:
        return self.environment in ("staging", "production")

    @property
    def has_organization(self) -> bool:
        return self.organization_id is not None

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions


# Convenience constant for local development
LocalDevAuthContext = AuthContext(
    actor_type="system",
    actor_id="local-dev",
    organization_id=LOCAL_DEV_ORGANIZATION_ID,
    permissions=[],
    scopes=[],
    environment="local",
    auth_method="local_test",
    is_mock_auth=True,
    is_authenticated=True,
    is_internal=True,
)

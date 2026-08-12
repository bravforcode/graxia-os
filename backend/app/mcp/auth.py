"""MCP authentication and organization context — validates organization scope."""
from __future__ import annotations

from uuid import UUID

from app.mcp.schemas import MCPAuthContext


def validate_org_context(
    auth: MCPAuthContext | None,
    required_org_id: UUID | None,
) -> bool:
    """Validate that the auth context has access to the required org.

    Returns True if:
    - No auth context AND no required org (public access)
    - System actor (bypasses check)
    - auth.organization_id matches required_org_id

    Returns False if org mismatch.
    """
    if auth is None:
        return required_org_id is None

    if auth.actor_type == "system" and auth.actor_id == "system":
        return True  # System bypass

    if auth.organization_id is None:
        return required_org_id is None

    if required_org_id is None:
        return True

    return auth.organization_id == required_org_id


def safe_org_not_found() -> None:
    """Raises a controlled org-mismatch exception.

    This is intentionally vague — never reveal whether the org exists.
    """
    raise PermissionError("Resource not found.")

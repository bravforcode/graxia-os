"""Canonical Phase 16 permission model and helpers."""
from __future__ import annotations

from collections.abc import Iterable

from app.auth.context import AuthContext

ALL_PERMISSIONS: tuple[str, ...] = (
    "system:read",
    "system:write",
    "org:read",
    "org:write",
    "funnel:read",
    "funnel:write",
    "products:read",
    "products:write",
    "orders:read",
    "orders:write",
    "delivery:read",
    "delivery:write",
    "leads:read",
    "leads:write",
    "analytics:read",
    "approvals:read",
    "approvals:write",
    "approvals:resolve",
    "mcp:read",
    "mcp:write",
    "mcp:admin",
    "runtime:read",
    "runtime:write",
    "runtime:requeue",
    "workflow:read",
    "workflow:run",
    "context:read",
    "context:write",
    "audit:read",
    "admin:read",
    "admin:write",
)

ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "viewer": (
        "system:read",
        "org:read",
        "funnel:read",
        "products:read",
        "orders:read",
        "delivery:read",
        "leads:read",
        "analytics:read",
        "approvals:read",
        "workflow:read",
        "context:read",
        "audit:read",
    ),
    "user": (
        "system:read",
        "org:read",
        "funnel:read",
        "funnel:write",
        "products:read",
        "products:write",
        "orders:read",
        "orders:write",
        "delivery:read",
        "delivery:write",
        "leads:read",
        "leads:write",
        "analytics:read",
        "approvals:read",
        "approvals:write",
        "mcp:read",
        "workflow:read",
        "workflow:run",
        "context:read",
        "audit:read",
    ),
    "operator": (
        *ALL_PERMISSIONS,
    ),
    "admin": ALL_PERMISSIONS,
    "service": ALL_PERMISSIONS,
    "system": ALL_PERMISSIONS,
    "agent": ALL_PERMISSIONS,
}


def normalize_permissions(values: Iterable[str] | None) -> list[str]:
    if not values:
        return []
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in values:
        val = str(raw or "").strip()
        if not val or val in seen:
            continue
        seen.add(val)
        normalized.append(val)
    return normalized


def permissions_for_role(role: str | None) -> list[str]:
    return list(ROLE_PERMISSIONS.get((role or "").strip().lower(), ()))


def auth_context_has_permission(auth: AuthContext | None, permission: str) -> bool:
    if auth is None:
        return False
    if auth.actor_type in {"system", "service", "agent"} and auth.actor_id in {"system", "local-dev"}:
        return True
    return permission in auth.permissions

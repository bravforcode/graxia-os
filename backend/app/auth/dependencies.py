"""FastAPI dependencies — extract AuthContext from request headers.

Usage in staging/production:
    async def my_endpoint(
        org: AuthContext = Depends(require_organization),
        ...
    ):
        org.organization_id  # Guaranteed non-None

Local dev fallback:
    async def my_endpoint(
        org: AuthContext = Depends(get_auth_context),
        ...
    ):
        org.organization_id  # Falls back to LOCAL_DEV_ORGANIZATION_ID
"""
from __future__ import annotations

import uuid
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status

from app.auth.context import AuthContext, LocalDevAuthContext, LOCAL_DEV_ORGANIZATION_ID
from app.auth.permissions import auth_context_has_permission, normalize_permissions, permissions_for_role
from app.config import settings


def _csv_header_values(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _request_id(request: Request, explicit: str | None) -> str:
    return (
        explicit
        or request.headers.get("X-Request-ID")
        or request.headers.get("X-Graxia-Request-Id")
        or getattr(request.state, "request_id", None)
        or str(uuid.uuid4())
    )


def _correlation_id(request: Request) -> str:
    return (
        request.headers.get("X-Correlation-ID")
        or request.headers.get("X-Graxia-Correlation-Id")
        or getattr(request.state, "correlation_id", None)
        or getattr(request.state, "request_id", None)
        or str(uuid.uuid4())
    )


def _role_permissions(request: Request, env: str, actor_type: str) -> list[str]:
    explicit = _csv_header_values(request.headers.get("X-Graxia-Permissions"))
    if explicit:
        return normalize_permissions(explicit)

    authenticated_role = str(getattr(request.state, "authenticated_role", "") or "").strip().lower()
    if authenticated_role:
        return permissions_for_role(authenticated_role)

    if env in ("local", "development", "test"):
        fallback_role = "admin" if actor_type in {"system", "service", "agent", "admin"} else "user"
        return permissions_for_role(fallback_role)

    return []


async def get_auth_context(
    request: Request,
    x_graxia_org_id: str | None = Header(None),
    x_graxia_actor_type: str | None = Header(None),
    x_graxia_actor_id: str | None = Header(None),
    x_graxia_request_id: str | None = Header(None),
    x_graxia_scopes: str | None = Header(None),
) -> AuthContext:
    """Extract AuthContext from request headers.

    - Staging/production: Requires X-Graxia-Org-Id header.
    - Local/test: Falls back to LocalDevAuthContext.

    Never returns None — always provides a valid context.
    """
    env = (settings.APP_ENV or "development").lower()

    request_id = _request_id(request, x_graxia_request_id)
    correlation_id = _correlation_id(request)
    actor_type = (
        x_graxia_actor_type
        or ("admin" if getattr(request.state, "authenticated_role", "") == "admin" else "")
        or ("user" if getattr(request.state, "authenticated_user_id", "") else "")
        or ("system" if env not in ("staging", "production") else "user")
    )
    actor_id = x_graxia_actor_id or getattr(request.state, "authenticated_user_id", None) or None
    auth_method = "bearer_jwt" if getattr(request.state, "auth_payload", None) else "local_test"
    scopes = normalize_permissions(_csv_header_values(x_graxia_scopes))

    if env in ("staging", "production"):
        # Require explicit org header
        if not x_graxia_org_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="X-Graxia-Org-Id header is required.",
            )
        try:
            org_id = UUID(x_graxia_org_id)
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid X-Graxia-Org-Id format.",
            )

        is_mock = env != "production" and org_id == LOCAL_DEV_ORGANIZATION_ID
        return AuthContext(
            actor_type=actor_type,
            actor_id=actor_id,
            organization_id=org_id,
            permissions=_role_permissions(request, env, actor_type),
            scopes=scopes,
            request_id=request_id,
            correlation_id=correlation_id,
            environment=env,
            auth_method=auth_method if not is_mock else "local_test",
            is_mock_auth=is_mock,
            is_authenticated=not is_mock or bool(getattr(request.state, "auth_payload", None)),
            is_internal=actor_type in {"system", "service", "agent"},
            is_customer=actor_type == "customer",
        )

    # Local / test: use local dev default
    org_id = LOCAL_DEV_ORGANIZATION_ID
    if x_graxia_org_id:
        try:
            org_id = UUID(x_graxia_org_id)
        except (ValueError, AttributeError):
            pass

    return AuthContext(
        actor_type=actor_type or "system",
        actor_id=actor_id or "local-dev",
        organization_id=org_id,
        permissions=_role_permissions(request, env, actor_type or "system"),
        scopes=scopes,
        request_id=request_id,
        correlation_id=correlation_id,
        environment=env,
        auth_method="local_test" if not getattr(request.state, "auth_payload", None) else "bearer_jwt",
        is_mock_auth=True,
        is_authenticated=True,
        is_internal=(actor_type or "system") in {"system", "service", "agent"},
        is_customer=(actor_type or "") == "customer",
    )


async def require_organization(
    auth: AuthContext = Depends(get_auth_context),
) -> AuthContext:
    """Dependency that requires a valid organization context.

    Raises 401 if no org context is available.
    This is the primary dependency for all org-scoped endpoints.
    """
    if not auth or not auth.has_organization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Organization context required.",
        )
    return auth


async def require_staging_auth(
    auth: AuthContext = Depends(get_auth_context),
) -> AuthContext:
    """Staging/production: requires real (non-mock) auth.

    Local/test: passes through.
    """
    if auth.is_staging_or_production and auth.is_mock_auth:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Real authentication required for staging/production.",
        )
    return auth


async def require_authenticated(
    auth: AuthContext = Depends(get_auth_context),
) -> AuthContext:
    if auth.is_staging_or_production and not auth.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return auth


def require_permission(permission: str):
    async def permission_dependency(
        auth: AuthContext = Depends(get_auth_context),
    ) -> AuthContext:
        if not auth_context_has_permission(auth, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions.",
            )
        return auth

    return permission_dependency


async def require_admin(
    auth: AuthContext = Depends(get_auth_context),
) -> AuthContext:
    if not auth_context_has_permission(auth, "admin:read"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions.",
        )
    return auth


async def optional_auth_context(
    request: Request,
    x_graxia_org_id: str | None = Header(None),
) -> AuthContext | None:
    """Optional auth context — returns None if no header provided.

    For endpoints that work both publicly and in org-scoped mode.
    """
    if not x_graxia_org_id:
        return None

    try:
        return await get_auth_context(
            request,
            x_graxia_org_id=x_graxia_org_id,
        )
    except HTTPException:
        return None

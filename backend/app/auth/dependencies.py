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
from app.auth.errors import MissingAuthError, OrgMismatchError
from app.config import settings


async def get_auth_context(
    request: Request,
    x_graxia_org_id: str | None = Header(None),
    x_graxia_actor_type: str | None = Header(None),
    x_graxia_actor_id: str | None = Header(None),
    x_graxia_request_id: str | None = Header(None),
) -> AuthContext:
    """Extract AuthContext from request headers.

    - Staging/production: Requires X-Graxia-Org-Id header.
    - Local/test: Falls back to LocalDevAuthContext.

    Never returns None — always provides a valid context.
    """
    env = (settings.APP_ENV or "development").lower()

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
            actor_type=x_graxia_actor_type or "user",
            actor_id=x_graxia_actor_id or None,
            organization_id=org_id,
            request_id=x_graxia_request_id or str(uuid.uuid4()),
            environment=env,
            is_mock_auth=is_mock,
        )

    # Local / test: use local dev default
    org_id = LOCAL_DEV_ORGANIZATION_ID
    if x_graxia_org_id:
        try:
            org_id = UUID(x_graxia_org_id)
        except (ValueError, AttributeError):
            pass

    return AuthContext(
        actor_type=x_graxia_actor_type or "system",
        actor_id=x_graxia_actor_id or "local-dev",
        organization_id=org_id,
        request_id=x_graxia_request_id or str(uuid.uuid4()),
        environment=env,
        is_mock_auth=True,
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

"""ASGI middleware — extracts AuthContext from request headers into request.state.

Mounted in main.py after the existing AuthMiddleware so that
request.state.auth_context is always available for downstream handlers.
"""
from __future__ import annotations

from collections.abc import Callable, Awaitable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.auth.context import AuthContext, LocalDevAuthContext
from app.auth.dependencies import get_auth_context
from app.config import settings
from app.core.errors import build_error_response
from app.core.request_context import get_correlation_id, get_request_id


class AuthContextMiddleware(BaseHTTPMiddleware):
    """Populates request.state.auth_context for all requests.

    - Staging/production: Parses X-Graxia-Org-Id header.
    - Local/test: Falls back to LocalDevAuthContext.

    This runs after the existing AuthMiddleware to ensure auth is established.
    """

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable]):
        env = (settings.APP_ENV or "development").lower()

        # Read headers
        org_id_header = request.headers.get("X-Graxia-Org-Id", "").strip()
        actor_type = request.headers.get("X-Graxia-Actor-Type", "").strip()
        actor_id = request.headers.get("X-Graxia-Actor-Id", "").strip()
        request_id = request.headers.get("X-Graxia-Request-Id", "").strip()

        if env in ("staging", "production") and not org_id_header:
            # Public/anon traffic (store browsing, login, Stripe webhooks,
            # delivery links, health) must not be blocked by the org gate.
            from app.middleware.auth import AuthLevel, classify_route, find_route_template

            template = find_route_template(request)
            level = classify_route(request.method, template) if template else AuthLevel.PUBLIC
            if level == AuthLevel.PUBLIC:
                request.state.auth_context = None
                return await call_next(request)

            # Authenticated request without an org header: resolve the org from
            # the JWT user's account instead of failing. Resolution errors must
            # NOT swallow downstream errors — call_next stays OUTSIDE the try.
            resolved_context = None
            try:
                from uuid import UUID

                from app.database import AsyncSessionLocal
                from app.middleware.auth import build_auth_context
                from app.models.user import User

                payload = await build_auth_context(request)
                user_id = payload.get("sub")
                if user_id:
                    async with AsyncSessionLocal() as db:
                        user = await db.get(User, UUID(str(user_id)))
                        if user and user.organization_id:
                            resolved_context = AuthContext(
                                actor_type="user",
                                actor_id=str(user.id),
                                organization_id=user.organization_id,
                                environment=env,
                                is_authenticated=True,
                                request_id=request_id or get_request_id(request),
                                correlation_id=get_correlation_id(request),
                            )
            except Exception:  # noqa: BLE001 — fall through to the org gate
                resolved_context = None

            if resolved_context is not None:
                request.state.auth_context = resolved_context
                return await call_next(request)

            # Block requests without org context in staging/production
            return build_error_response(
                request,
                code="ORG_REQUIRED",
                message="Organization context is required",
                status_code=401,
            )

            # Block requests without org context in staging/production
            return build_error_response(
                request,
                code="ORG_REQUIRED",
                message="Organization context is required",
                status_code=401,
            )

        # Build context
        if org_id_header:
            try:
                from uuid import UUID
                org_uuid = UUID(org_id_header)
            except (ValueError, AttributeError):
                return build_error_response(
                    request,
                    code="AUTH_INVALID",
                    message="Authentication is invalid",
                    status_code=401,
                )

            is_mock = env != "production" and str(org_uuid) == "00000000-0000-0000-0000-000000000001"
            request.state.auth_context = AuthContext(
                actor_type=actor_type or "user",
                actor_id=actor_id or None,
                organization_id=org_uuid,
                environment=env,
                is_mock_auth=is_mock,
                request_id=request_id or get_request_id(request),
                correlation_id=get_correlation_id(request),
                is_authenticated=True,
                is_internal=actor_type in {"service", "system", "agent"},
                is_customer=actor_type == "customer",
            )
        else:
            # Local/test fallback
            request.state.auth_context = LocalDevAuthContext

        return await call_next(request)

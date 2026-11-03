"""ASGI middleware — extracts AuthContext from request headers into request.state.

Mounted in main.py after the existing AuthMiddleware so that
request.state.auth_context is always available for downstream handlers.
"""
from __future__ import annotations

from collections.abc import Callable, Awaitable
from uuid import UUID

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.auth.context import AuthContext, LocalDevAuthContext
from app.auth.dependencies import get_auth_context
from app.config import settings
from app.core.errors import build_error_response
from app.core.request_context import get_correlation_id, get_request_id


class AuthContextMiddleware(BaseHTTPMiddleware):
    """Populates request.state.auth_context for all requests.

    - Staging/production: Resolves verified JWT/session and persisted user tenant.
    - Local/test: Falls back to LocalDevAuthContext.

    This runs after the existing AuthMiddleware to ensure auth is established.
    """

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable]):
        env = (settings.APP_ENV or "development").lower()

        # Request and actor headers are useful local/test fixture inputs, but
        # actor identity is never caller-controlled in staging/production.
        org_id_header = request.headers.get("X-Graxia-Org-Id", "").strip()
        actor_type = request.headers.get("X-Graxia-Actor-Type", "").strip()
        actor_id = request.headers.get("X-Graxia-Actor-Id", "").strip()
        request_id = request.headers.get("X-Graxia-Request-Id", "").strip()

        if env in ("staging", "production"):
            # Public/anon traffic (store browsing, login, Stripe webhooks,
            # delivery links, health) must not be blocked by the org gate.
            from app.middleware.auth import AuthLevel, classify_route, find_route_template

            template = find_route_template(request)
            level = classify_route(request.method, template) if template else AuthLevel.PUBLIC
            internal_route = template and (
                request.method.upper(), template
            ) in {
                ("POST", "/api/v1/revenue-bridge/events"),
                ("POST", "/api/v1/integrations/alerts/telegram"),
            }

            if internal_route or level == AuthLevel.PUBLIC:
                # Internal routes: AuthMiddleware performs the authoritative
                # internal-token verification. Never build a context from
                # caller headers here.
                request.state.auth_context = None
                return await call_next(request)

            try:
                # Use the same verified persisted-user resolver as API dependencies.
                request.state.auth_context = await get_auth_context(
                    request, x_graxia_org_id=org_id_header or None,
                    x_graxia_actor_type=None, x_graxia_actor_id=None,
                    x_graxia_request_id=request_id or None, x_graxia_scopes=None,
                )
            except HTTPException as exc:
                request.state.auth_context = None
                return build_error_response(
                    request, code="AUTH_INVALID", message="Authentication is invalid",
                    status_code=exc.status_code,
                )
            return await call_next(request)

        # Build context
        if org_id_header:
            try:
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

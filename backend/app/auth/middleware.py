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

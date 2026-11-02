"""ASGI middleware — extracts AuthContext from request headers into request.state.

Mounted in main.py after the existing AuthMiddleware so that
request.state.auth_context is always available for downstream handlers.
"""
from __future__ import annotations

from collections.abc import Callable, Awaitable
from uuid import UUID

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.auth.context import AuthContext, LocalDevAuthContext
from app.middleware.auth import (
    AuthLevel,
    build_auth_context,
    classify_route,
    find_route_template,
)
from app.config import settings
from app.core.errors import build_error_response
from app.core.request_context import get_correlation_id, get_request_id


class AuthContextMiddleware(BaseHTTPMiddleware):
    """Populates request.state.auth_context for all requests.

    - Staging/production: Uses verified JWT or internal authentication only.
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
            template = find_route_template(request)
            level = classify_route(request.method, template) if template else AuthLevel.PUBLIC
            internal_route = template and (
                request.method.upper(), template
            ) in {
                ("POST", "/api/v1/revenue-bridge/events"),
                ("POST", "/api/v1/integrations/alerts/telegram"),
            }

            if internal_route:
                # AuthMiddleware performs the authoritative internal-token
                # verification later in the stack. Do not manufacture a
                # service context from arbitrary actor headers here.
                request.state.auth_context = None
                return await call_next(request)

            if level == AuthLevel.PUBLIC:
                request.state.auth_context = None
                return await call_next(request)

            try:
                payload = await build_auth_context(request)
                user_id = str(payload.get("sub") or "")
                role = str(payload.get("role") or "user").strip().lower()
                resolved_actor_type = (
                    role if role in {"admin", "service", "system", "agent"} else "user"
                )
                token_org_id = None
                if payload.get("organization_id"):
                    token_org_id = UUID(str(payload["organization_id"]))

                header_org_id = None
                if org_id_header:
                    header_org_id = UUID(org_id_header)
                if token_org_id and header_org_id and token_org_id != header_org_id:
                    return build_error_response(
                        request,
                        code="AUTH_INVALID",
                        message="Authentication is invalid",
                        status_code=401,
                    )

                organization_id = token_org_id or header_org_id
                if organization_id is None and user_id:
                    from app.database import AsyncSessionLocal
                    from app.models.user import User

                    async with AsyncSessionLocal() as db:
                        user = await db.get(User, UUID(user_id))
                        organization_id = user.organization_id if user else None

                if organization_id is None:
                    return build_error_response(
                        request,
                        code="ORG_REQUIRED",
                        message="Organization context is required",
                        status_code=401,
                    )

                request.state.auth_context = AuthContext(
                    actor_type=resolved_actor_type,
                    actor_id=user_id or None,
                    organization_id=organization_id,
                    environment=env,
                    auth_method="bearer_jwt",
                    is_authenticated=True,
                    is_internal=resolved_actor_type in {"service", "system", "agent"},
                    request_id=request_id or get_request_id(request),
                    correlation_id=get_correlation_id(request),
                )
            except (TypeError, ValueError, KeyError):
                return build_error_response(
                    request,
                    code="AUTH_INVALID",
                    message="Authentication is invalid",
                    status_code=401,
                )
            except Exception:  # noqa: BLE001 — fail closed on auth resolution errors
                return build_error_response(
                    request,
                    code="AUTH_REQUIRED",
                    message="Authentication required",
                    status_code=401,
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

"""Authentication middleware and route classification helpers."""
from __future__ import annotations

import hashlib
import hmac
from enum import Enum
from typing import Any

from fastapi import HTTPException, Request, Security, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Match

from app.config import settings
from app.core.auth import (
    create_access_token,
    decode_access_token,
    extract_bearer_token,
    get_password_hash,
    verify_password,
)
from app.services.audit_service import log_audit_event
from app.services.session_service import SessionService

security = HTTPBearer(auto_error=False)


class AuthLevel(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    AUTHENTICATED = "authenticated"
    OPERATOR = "operator"
    ADMIN = "admin"
    BLOCKED = "blocked"


PUBLIC_ROUTES: set[tuple[str, str]] = {
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/social-login"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/logout"),
    ("GET", "/health"),
    ("GET", "/"),
    ("GET", "/favicon.ico"),
}

BLOCKED_PREFIXES = ("/docs", "/redoc", "/openapi.json", "/metrics", "/flower", "/admin")
OPERATOR_PREFIXES = ("/api/v1/approvals", "/api/v1/runs")
OPERATOR_ROUTES: set[tuple[str, str]] = {
    ("POST", "/api/v1/commands/execute"),
    ("POST", "/api/v1/system/scan"),
    ("POST", "/api/v1/system/scan/now"),
    ("POST", "/api/v1/system/brief"),
    ("POST", "/api/v1/system/brief/now"),
}
ADMIN_PREFIXES = ("/api/v1/events", "/api/v1/scrapers", "/api/v1/admin")
ADMIN_ROUTE_PREFIXES = ("/api/v1/system",)
CSRF_EXEMPT_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/social-login",
    "/api/v1/auth/refresh",
    "/api/v1/auth/logout",
    "/api/v1/integrations/alerts/telegram",
    "/api/v1/contacts/bulk",
}
INTERNAL_TOKEN_ROUTES: set[tuple[str, str]] = {
    ("POST", "/api/v1/integrations/alerts/telegram"),
}

ROLE_ORDER = {
    "viewer": 0,
    "user": 1,
    "operator": 2,
    "admin": 3,
}


def is_blocked_surface(path: str) -> bool:
    return path == "/metrics" or path.startswith(BLOCKED_PREFIXES)


def classify_route(method: str, route_path: str) -> AuthLevel:
    key = (method.upper(), route_path)
    if key in INTERNAL_TOKEN_ROUTES:
        return AuthLevel.INTERNAL
    if is_blocked_surface(route_path):
        return AuthLevel.BLOCKED
    if key in PUBLIC_ROUTES:
        return AuthLevel.PUBLIC
    if key in OPERATOR_ROUTES or route_path.startswith(OPERATOR_PREFIXES):
        return AuthLevel.OPERATOR
    if route_path.startswith(ADMIN_PREFIXES):
        return AuthLevel.ADMIN
    if route_path.startswith(ADMIN_ROUTE_PREFIXES):
        if key in OPERATOR_ROUTES:
            return AuthLevel.OPERATOR
        return AuthLevel.ADMIN
    if route_path.startswith("/api/v1") or route_path.startswith("/obsidian"):
        return AuthLevel.AUTHENTICATED
    return AuthLevel.PUBLIC


def route_controls(method: str, route_path: str) -> list[str]:
    controls = ["security_headers", "rate_limit"]
    if (method.upper(), route_path) in INTERNAL_TOKEN_ROUTES:
        controls.append("internal_token")
        return controls
    level = classify_route(method, route_path)
    if level in {AuthLevel.AUTHENTICATED, AuthLevel.OPERATOR, AuthLevel.ADMIN}:
        controls.append("jwt_auth")
    if method.upper() in {"POST", "PUT", "PATCH", "DELETE"} and route_path not in CSRF_EXEMPT_PATHS:
        controls.append("csrf")
    return controls


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if forwarded_for:
        return forwarded_for
    return request.client.host if request.client else "unknown"


def get_device_fingerprint(request: Request) -> str:
    explicit = request.headers.get("x-device-fingerprint", "").strip()
    if explicit:
        return explicit[:128]
    material = "|".join(
        [
            request.headers.get("user-agent", ""),
            get_client_ip(request),
            request.headers.get("accept-language", ""),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def extract_access_token_from_request(request: Request) -> str | None:
    cookie_token = request.cookies.get(settings.ACCESS_COOKIE_NAME)
    if cookie_token:
        return cookie_token
    return extract_bearer_token(request.headers.get("Authorization"))


def role_satisfies(required: AuthLevel, actual_role: str) -> bool:
    if required == AuthLevel.AUTHENTICATED:
        return ROLE_ORDER.get(actual_role, -1) >= ROLE_ORDER["user"]
    if required == AuthLevel.OPERATOR:
        return ROLE_ORDER.get(actual_role, -1) >= ROLE_ORDER["operator"]
    if required == AuthLevel.ADMIN:
        return ROLE_ORDER.get(actual_role, -1) >= ROLE_ORDER["admin"]
    return required == AuthLevel.PUBLIC


def find_route_template(request: Request) -> str | None:
    for route in request.app.router.routes:
        match, _ = route.matches(request.scope)
        if match == Match.FULL:
            return getattr(route, "path", request.url.path)
    return None


async def build_auth_context(request: Request) -> dict[str, Any]:
    token = extract_access_token_from_request(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(token)
    session_id = str(payload.get("session_id") or "")
    if session_id:
        session_service = SessionService(getattr(request.app.state, "redis", None))
        if not await session_service.is_session_active(session_id):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session is no longer active",
                headers={"WWW-Authenticate": "Bearer"},
            )
    return payload


class AuthMiddleware(BaseHTTPMiddleware):
    """Fail-closed route protection using the mounted app routes."""

    async def dispatch(self, request: Request, call_next):
        route_path = find_route_template(request)
        path = request.url.path

        if route_path is None:
            if is_blocked_surface(path) and settings.STRICT_BOOTSTRAP:
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            return JSONResponse({"detail": "Forbidden"}, status_code=403)

        required_level = classify_route(request.method, route_path)
        if required_level == AuthLevel.BLOCKED and settings.STRICT_BOOTSTRAP:
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        if (request.method.upper(), route_path) in INTERNAL_TOKEN_ROUTES:
            configured = (settings.ALERTMANAGER_WEBHOOK_TOKEN or "").strip()
            provided = request.headers.get("X-Alertmanager-Token", "").strip()
            authorization = request.headers.get("Authorization", "")
            if authorization.lower().startswith("bearer "):
                provided = authorization.split(" ", 1)[1].strip()
            if not configured or not hmac.compare_digest(configured, provided):
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
            request.state.internal_token_authenticated = True
            return await call_next(request)
        if required_level == AuthLevel.PUBLIC:
            return await call_next(request)

        try:
            payload = await build_auth_context(request)
        except HTTPException as exc:
            return JSONResponse(
                {"detail": exc.detail},
                status_code=exc.status_code,
                headers=exc.headers or {},
            )

        user_role = str(payload.get("role") or "user")
        if not role_satisfies(required_level, user_role):
            await log_audit_event(
                app=request.app,
                action="auth.forbidden",
                event_type="privilege_escalation_attempt",
                event_category="security",
                severity="CRITICAL",
                outcome="blocked",
                success=False,
                metadata={"required_level": required_level.value, "actual_role": user_role},
                user_id=str(payload.get("sub") or ""),
                session_id=str(payload.get("session_id") or ""),
                ip_address=get_client_ip(request),
                user_agent=request.headers.get("user-agent"),
                request_path=path,
                request_method=request.method,
            )
            return JSONResponse({"detail": "Forbidden"}, status_code=403)

        request.state.auth_payload = payload
        request.state.session_id = str(payload.get("session_id") or "")
        request.state.authenticated_role = user_role
        request.state.authenticated_user_id = str(payload.get("sub") or "")
        return await call_next(request)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {
        "user_id": str(user_id),
        "roles": [payload.get("role", "user")],
        "email": payload.get("email"),
        "session_id": payload.get("session_id"),
    }


async def get_current_active_user(current_user: dict[str, Any] = Security(get_current_user)) -> dict[str, Any]:
    return current_user


async def require_role(required_role: str, current_user: dict[str, Any] = Security(get_current_user)) -> dict[str, Any]:
    user_roles = current_user.get("roles", [])
    if required_role not in user_roles and "admin" not in user_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. Required role: {required_role}",
        )
    return current_user


async def verify_api_key(api_key: str) -> bool:
    configured_key = (settings.API_KEY or "").strip()
    return bool(configured_key) and api_key == configured_key

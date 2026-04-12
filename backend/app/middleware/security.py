"""Security middleware, headers, and CSRF helpers."""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.config import settings
from app.core.monitoring import metrics_collector
from app.middleware.auth import CSRF_EXEMPT_PATHS
from app.services.audit_service import log_audit_event

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "X-DNS-Prefetch-Control": "off",
}
HEADERS_TO_REMOVE = {"Server", "X-Powered-By", "X-AspNet-Version", "X-AspNetMvc-Version"}


def generate_csrf_token(session_id: str, secret: str | None = None) -> str:
    secret = (secret or settings.CSRF_SIGNING_SECRET).encode("utf-8")
    random_part = secrets.token_bytes(32)
    message = random_part + session_id.encode("utf-8")
    signature = hmac.new(secret, message, hashlib.sha256).digest()
    return f"{base64.urlsafe_b64encode(random_part).decode()}.{base64.urlsafe_b64encode(signature).decode()}"


def validate_csrf_token_signature(token: str, session_id: str, secret: str | None = None) -> bool:
    if not token or "." not in token or not session_id:
        return False
    try:
        random_b64, signature_b64 = token.split(".", 1)
        random_part = base64.urlsafe_b64decode(random_b64.encode("utf-8"))
        provided_signature = base64.urlsafe_b64decode(signature_b64.encode("utf-8"))
    except Exception:
        return False
    secret = (secret or settings.CSRF_SIGNING_SECRET).encode("utf-8")
    expected_signature = hmac.new(
        secret,
        random_part + session_id.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return hmac.compare_digest(expected_signature, provided_signature)


def _normalize_csrf_token(token: str | None) -> str | None:
    if token is None:
        return None
    return token.strip().strip('"')


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add production-grade response headers."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            if header == "Strict-Transport-Security" and not settings.STRICT_BOOTSTRAP:
                continue
            response.headers[header] = value
        for header in HEADERS_TO_REMOVE:
            if header in response.headers:
                del response.headers[header]
        return response


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double-submit CSRF validation for unsafe authenticated requests."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method not in UNSAFE_METHODS or path in CSRF_EXEMPT_PATHS:
            return await call_next(request)

        if not hasattr(request.state, "session_id") or not request.state.session_id:
            return await call_next(request)

        cookie_token = _normalize_csrf_token(request.cookies.get(settings.CSRF_COOKIE_NAME))
        header_token = _normalize_csrf_token(request.headers.get("X-CSRF-Token"))
        if not cookie_token or not header_token:
            metrics_collector.record_csrf_violation(path)
            await log_audit_event(
                app=request.app,
                action="security.csrf",
                event_type="csrf_violation",
                event_category="security",
                severity="HIGH",
                outcome="blocked",
                success=False,
                metadata={"reason": "missing_token"},
                user_id=getattr(request.state, "authenticated_user_id", None),
                session_id=getattr(request.state, "session_id", None),
                ip_address=request.client.host if request.client else "unknown",
                user_agent=request.headers.get("user-agent"),
                request_path=path,
                request_method=request.method,
            )
            return JSONResponse({"detail": "CSRF token missing"}, status_code=403)

        if not hmac.compare_digest(cookie_token, header_token):
            metrics_collector.record_csrf_violation(path)
            await log_audit_event(
                app=request.app,
                action="security.csrf",
                event_type="csrf_violation",
                event_category="security",
                severity="HIGH",
                outcome="blocked",
                success=False,
                metadata={"reason": "token_mismatch"},
                user_id=getattr(request.state, "authenticated_user_id", None),
                session_id=getattr(request.state, "session_id", None),
                ip_address=request.client.host if request.client else "unknown",
                user_agent=request.headers.get("user-agent"),
                request_path=path,
                request_method=request.method,
            )
            return JSONResponse({"detail": "CSRF token invalid"}, status_code=403)

        if not validate_csrf_token_signature(cookie_token, request.state.session_id):
            metrics_collector.record_csrf_violation(path)
            await log_audit_event(
                app=request.app,
                action="security.csrf",
                event_type="csrf_violation",
                event_category="security",
                severity="HIGH",
                outcome="blocked",
                success=False,
                metadata={"reason": "forged_token"},
                user_id=getattr(request.state, "authenticated_user_id", None),
                session_id=getattr(request.state, "session_id", None),
                ip_address=request.client.host if request.client else "unknown",
                user_agent=request.headers.get("user-agent"),
                request_path=path,
                request_method=request.method,
            )
            return JSONResponse({"detail": "CSRF token forged"}, status_code=403)

        return await call_next(request)


class InputSanitizationMiddleware(BaseHTTPMiddleware):
    """Reject obviously malicious input fragments early."""

    SQL_INJECTION_PATTERNS = [
        r"(\bUNION\b.*\bSELECT\b)",
        r"(\bDROP\b.*\bTABLE\b)",
        r"(\bINSERT\b.*\bINTO\b)",
        r"(\bDELETE\b.*\bFROM\b)",
        r"(--|\#|/\*|\*/)",
    ]

    XSS_PATTERNS = [
        r"<script[^>]*>.*?</script>",
        r"javascript:",
        r"onerror\s*=",
        r"onload\s*=",
    ]

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.sql_regex = re.compile("|".join(self.SQL_INJECTION_PATTERNS), re.IGNORECASE)
        self.xss_regex = re.compile("|".join(self.XSS_PATTERNS), re.IGNORECASE)

    async def dispatch(self, request: Request, call_next):
        for _, value in request.query_params.items():
            if self._is_suspicious(value):
                return Response(content="Suspicious input detected", status_code=400)
        if self._is_suspicious(str(request.url.path)):
            return Response(content="Suspicious path detected", status_code=400)
        return await call_next(request)

    def _is_suspicious(self, value: str) -> bool:
        return bool(self.sql_regex.search(value) or self.xss_regex.search(value))


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Limit request body size to reduce trivial abuse and DoS."""

    def __init__(self, app: ASGIApp, max_size: int = 10 * 1024 * 1024):
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_size:
            return Response(
                content=f"Request body too large. Maximum size: {self.max_size} bytes",
                status_code=413,
            )
        return await call_next(request)

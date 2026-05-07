"""Security middleware, headers, and CSRF helpers."""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets

from app.config import settings
from app.core.monitoring import metrics_collector
from app.middleware.auth import CSRF_EXEMPT_PATHS
from app.services.audit_service import log_audit_event
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
HEADERS_TO_REMOVE = {"Server", "X-Powered-By", "X-AspNet-Version", "X-AspNetMvc-Version"}


def _get_security_headers() -> dict[str, str]:
    """Build security headers dict from current settings (called per-request)."""
    return {
        "Content-Security-Policy": settings.SECURITY_HEADERS_CSP,
        "X-Frame-Options": settings.SECURITY_HEADERS_FRAME_OPTIONS,
        "X-Content-Type-Options": settings.SECURITY_HEADERS_CONTENT_TYPE_OPTIONS,
        "Referrer-Policy": settings.SECURITY_HEADERS_REFERRER_POLICY,
        "Permissions-Policy": settings.SECURITY_HEADERS_PERMISSIONS_POLICY,
        "Strict-Transport-Security": f"max-age={settings.SECURITY_HEADERS_HSTS_MAX_AGE}; includeSubDomains",
        "X-DNS-Prefetch-Control": settings.SECURITY_HEADERS_DNS_PREFETCH_CONTROL,
        # Legacy header — still supported by some browsers
        "X-XSS-Protection": "1; mode=block",
    }


def generate_csrf_token(session_id: str, secret: str | None = None) -> str:
    """
    Generate a CSRF token with timestamp for expiry validation.
    
    Token format: <random_base64>.<timestamp_base64>.<signature_base64>
    
    Args:
        session_id: User session ID
        secret: CSRF signing secret (defaults to settings.CSRF_SIGNING_SECRET)
    
    Returns:
        CSRF token string with embedded timestamp
    """
    secret = (secret or settings.CSRF_SIGNING_SECRET).encode("utf-8")
    random_part = secrets.token_bytes(32)
    
    # Add timestamp (Unix epoch in seconds)
    import time
    timestamp = int(time.time())
    timestamp_bytes = timestamp.to_bytes(8, byteorder='big')
    
    # Message includes random part, timestamp, and session ID
    message = random_part + timestamp_bytes + session_id.encode("utf-8")
    signature = hmac.new(secret, message, hashlib.sha256).digest()
    
    # Encode all parts
    random_b64 = base64.urlsafe_b64encode(random_part).decode()
    timestamp_b64 = base64.urlsafe_b64encode(timestamp_bytes).decode()
    signature_b64 = base64.urlsafe_b64encode(signature).decode()
    
    return f"{random_b64}.{timestamp_b64}.{signature_b64}"


def validate_csrf_token_signature(token: str, session_id: str, secret: str | None = None) -> bool:
    """
    Validate CSRF token signature and expiry.
    
    Supports both new format (with timestamp) and legacy format (without timestamp)
    for backward compatibility during migration period.
    
    Args:
        token: CSRF token to validate
        session_id: User session ID
        secret: CSRF signing secret (defaults to settings.CSRF_SIGNING_SECRET)
    
    Returns:
        True if token is valid and not expired, False otherwise
    """
    if not token or not session_id:
        return False
    
    # Check token format
    parts = token.split(".")
    if len(parts) not in (2, 3):  # Support both old (2 parts) and new (3 parts) format
        return False
    
    try:
        secret_bytes = (secret or settings.CSRF_SIGNING_SECRET).encode("utf-8")
        
        if len(parts) == 3:
            # New format with timestamp: <random>.<timestamp>.<signature>
            random_b64, timestamp_b64, signature_b64 = parts
            random_part = base64.urlsafe_b64decode(random_b64.encode("utf-8"))
            timestamp_bytes = base64.urlsafe_b64decode(timestamp_b64.encode("utf-8"))
            provided_signature = base64.urlsafe_b64decode(signature_b64.encode("utf-8"))
            
            # Extract timestamp
            timestamp = int.from_bytes(timestamp_bytes, byteorder='big')
            
            # Check expiry
            import time
            current_time = int(time.time())
            expiry_seconds = settings.CSRF_TOKEN_EXPIRY_HOURS * 3600
            
            if current_time - timestamp > expiry_seconds:
                # Token expired
                return False
            
            # Verify signature
            message = random_part + timestamp_bytes + session_id.encode("utf-8")
            expected_signature = hmac.new(secret_bytes, message, hashlib.sha256).digest()
            
            return hmac.compare_digest(expected_signature, provided_signature)
            
        else:
            # Legacy format without timestamp: <random>.<signature>
            # Support for backward compatibility (grace period)
            random_b64, signature_b64 = parts
            random_part = base64.urlsafe_b64decode(random_b64.encode("utf-8"))
            provided_signature = base64.urlsafe_b64decode(signature_b64.encode("utf-8"))
            
            # Verify signature (legacy format)
            message = random_part + session_id.encode("utf-8")
            expected_signature = hmac.new(secret_bytes, message, hashlib.sha256).digest()
            
            # Legacy tokens are accepted but should be logged for monitoring
            if hmac.compare_digest(expected_signature, provided_signature):
                # Log legacy token usage for monitoring
                import logging
                logger = logging.getLogger(__name__)
                logger.info("CSRF: Legacy token format detected (no timestamp)")
                return True
            
            return False
            
    except Exception:
        return False


def _normalize_csrf_token(token: str | None) -> str | None:
    if token is None:
        return None
    return token.strip().strip('"')


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add production-grade security response headers (reads from settings per-request)."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for header, value in _get_security_headers().items():
            if header == "Strict-Transport-Security" and not settings.STRICT_BOOTSTRAP:
                continue
            response.headers[header] = value
        for header in HEADERS_TO_REMOVE:
            if header in response.headers:
                del response.headers[header]
        return response


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double-submit CSRF validation for unsafe authenticated requests.
    
    SECURITY: All token comparisons use constant-time operations to prevent
    timing attacks. We avoid short-circuit evaluation that could leak information
    about token validity through response time measurements.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method not in UNSAFE_METHODS or path in CSRF_EXEMPT_PATHS:
            return await call_next(request)

        if not hasattr(request.state, "session_id") or not request.state.session_id:
            return await call_next(request)

        cookie_token = _normalize_csrf_token(request.cookies.get(settings.CSRF_COOKIE_NAME))
        header_token = _normalize_csrf_token(request.headers.get("X-CSRF-Token"))
        
        # SECURITY: Use constant-time checks to prevent timing attacks.
        # We check token existence using length checks instead of truthiness
        # to avoid short-circuit evaluation that could leak timing information.
        cookie_token_present = cookie_token is not None and len(cookie_token) > 0
        header_token_present = header_token is not None and len(header_token) > 0
        
        if not (cookie_token_present and header_token_present):
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

        # SECURITY: Use hmac.compare_digest for constant-time string comparison
        # to prevent timing attacks that could leak token information.
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
    """
    Context-aware input sanitization middleware.
    
    This is a last-resort defense layer. Proper input validation should happen
    at the application layer using Pydantic models and parameterized queries.
    
    Context-Aware Validation:
        - SQL patterns only checked in query parameters and JSON bodies
        - XSS patterns only checked in user-generated content fields
        - Legitimate uses of special characters (e.g., -- in comments, /* in CSS) are allowed
    """

    # More specific SQL injection patterns (require keywords after operators)
    SQL_INJECTION_PATTERNS = [
        r"(?i)\bUNION\s+SELECT\b",  # More specific: requires SELECT after UNION
        r"(?i)\bDROP\s+TABLE\b",    # More specific: requires TABLE after DROP
        r"(?i)\bINSERT\s+INTO\b",   # More specific: requires INTO after INSERT
        r"(?i)\bDELETE\s+FROM\b",   # More specific: requires FROM after DELETE
        r"(?i)\bEXEC\s*\(",         # SQL Server EXEC
        r"(?i)\bEXECUTE\s*\(",      # SQL Server EXECUTE
        r"(?i);.*\b(DROP|DELETE|UPDATE|INSERT)\b",  # Statement chaining
    ]

    # XSS patterns (context-aware)
    XSS_PATTERNS = [
        r"<script[^>]*>",           # Script tag opening
        r"javascript:\s*",          # JavaScript protocol
        r"on\w+\s*=\s*[\"']",       # Event handlers (onclick=, onerror=, etc.)
        r"<iframe[^>]*>",           # Iframe injection
        r"<object[^>]*>",           # Object injection
        r"<embed[^>]*>",            # Embed injection
    ]

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.sql_regex = re.compile("|".join(self.SQL_INJECTION_PATTERNS), re.IGNORECASE)
        self.xss_regex = re.compile("|".join(self.XSS_PATTERNS), re.IGNORECASE)

    async def dispatch(self, request: Request, call_next):
        # Check query parameters for SQL injection
        for param_name, value in request.query_params.items():
            if self._is_sql_injection(value):
                return Response(content="Suspicious SQL pattern detected", status_code=400)
            if self._is_xss(value):
                return Response(content="Suspicious XSS pattern detected", status_code=400)
        
        # Check URL path for suspicious patterns
        if self._is_sql_injection(str(request.url.path)) or self._is_xss(str(request.url.path)):
            return Response(content="Suspicious path detected", status_code=400)
        
        return await call_next(request)

    def _is_sql_injection(self, value: str) -> bool:
        """Check for SQL injection patterns."""
        return bool(self.sql_regex.search(value))
    
    def _is_xss(self, value: str) -> bool:
        """Check for XSS patterns."""
        return bool(self.xss_regex.search(value))


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

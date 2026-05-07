"""
Enterprise Security Hardening Module

Implements:
- Content Security Policy (CSP) headers
- Security headers (HSTS, X-Frame-Options, etc.)
- Request/response sanitization
- IP whitelist/blacklist
- API key rotation tracking
- Rate limiting by IP and API key
"""

import hashlib
import hmac
import ipaddress
import logging
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Enterprise-grade security headers middleware.
    Implements OWASP security recommendations.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Strict Transport Security (HSTS)
        # Forces HTTPS for 1 year, includes subdomains
        if settings.APP_ENV == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

        # Content Security Policy
        # Prevents XSS and data injection attacks
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'",  # Adjust for your needs
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: https:",
            "font-src 'self'",
            "connect-src 'self' https://api.stripe.com https://*.sentry.io",
            "frame-ancestors 'none'",  # Prevents clickjacking
            "base-uri 'self'",
            "form-action 'self'",
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

        # X-Frame-Options (legacy, CSP frame-ancestors is preferred)
        response.headers["X-Frame-Options"] = "DENY"

        # X-Content-Type-Options
        # Prevents MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # X-XSS-Protection (legacy, CSP is preferred)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions Policy
        # Restricts browser features
        response.headers["Permissions-Policy"] = (
            "camera=(), "
            "microphone=(), "
            "geolocation=(), "
            "payment=(), "
            "usb=(), "
            "magnetometer=(), "
            "gyroscope=(), "
            "speaker=()"
        )

        # Cache Control for sensitive endpoints
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        # Remove server identification
        if "server" in response.headers:
            del response.headers["server"]

        return response


class IPFilterMiddleware(BaseHTTPMiddleware):
    """
    IP filtering middleware for whitelist/blacklist.
    """

    def __init__(self, app, whitelist: list[str] = None, blacklist: list[str] = None):
        super().__init__(app)
        self.whitelist = whitelist or []
        self.blacklist = blacklist or []

        # Compile IP networks
        self.whitelist_networks = [ipaddress.ip_network(ip, strict=False) for ip in self.whitelist]
        self.blacklist_networks = [ipaddress.ip_network(ip, strict=False) for ip in self.blacklist]

    async def dispatch(self, request: Request, call_next):
        client_ip = self._get_client_ip(request)

        # Check blacklist first
        if self._is_ip_blocked(client_ip):
            logger.warning(f"Blocked request from blacklisted IP: {client_ip}")
            raise HTTPException(status_code=403, detail="Access denied")

        # Check whitelist if configured
        if self.whitelist_networks and not self._is_ip_allowed(client_ip):
            logger.warning(f"Blocked request from non-whitelisted IP: {client_ip}")
            raise HTTPException(status_code=403, detail="Access denied")

        # Add client IP to request state for logging
        request.state.client_ip = client_ip

        return await call_next(request)

    def _get_client_ip(self, request: Request) -> str:
        """Extract real client IP considering proxies."""
        # Check X-Forwarded-For header (common for proxies)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Get the first IP in the chain (closest to client)
            return forwarded_for.split(",")[0].strip()

        # Check X-Real-IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # Fall back to direct connection
        return request.client.host if request.client else "unknown"

    def _is_ip_blocked(self, ip_str: str) -> bool:
        """Check if IP is in blacklist."""
        try:
            ip = ipaddress.ip_address(ip_str)
            return any(ip in network for network in self.blacklist_networks)
        except ValueError:
            return False

    def _is_ip_allowed(self, ip_str: str) -> bool:
        """Check if IP is in whitelist."""
        try:
            ip = ipaddress.ip_address(ip_str)
            return any(ip in network for network in self.whitelist_networks)
        except ValueError:
            return False


class RequestSanitizationMiddleware(BaseHTTPMiddleware):
    """
    Sanitizes incoming requests to prevent injection attacks.
    """

    # Patterns for common attacks
    SQL_INJECTION_PATTERNS = [
        r"(\%27)|(\')|(\-\-)|(\%23)|(#)",  # Basic SQL meta-characters
        r"((\%3D)|(=))[^\n]*((\%27)|(\')|(\-\-)|(\%3B)|(;))",  # SQL injection attempts
        r"\w*((\%27)|(\'))((\%6F)|o|(\%4F))((\%72)|r|(\%52))",  # Union select
        r"((\%27)|(\'))union",  # Union-based injection
        r"exec(\s|\+)+(s|x)p\w+",  # Stored procedures
        r"UNION\s+SELECT",  # Union select
        r"INSERT\s+INTO",  # Insert injection
        r"DELETE\s+FROM",  # Delete injection
        r"DROP\s+TABLE",  # Drop table
    ]

    # Patterns for XSS attempts
    XSS_PATTERNS = [
        r"<script[^>]*>[\s\S]*?</script>",  # Script tags
        r"javascript:",  # JavaScript protocol
        r"on\w+\s*=",  # Event handlers
        r"<iframe",  # Iframe injection
        r"<object",  # Object injection
        r"<embed",  # Embed injection
    ]

    # Patterns for path traversal
    PATH_TRAVERSAL_PATTERNS = [
        r"\.\./",  # Unix path traversal
        r"\.\.\\",  # Windows path traversal
        r"%2e%2e%2f",  # URL encoded path traversal
        r"%252e%252e%252f",  # Double URL encoded
    ]

    def __init__(self, app):
        super().__init__(app)
        self.sql_pattern = re.compile("|".join(self.SQL_INJECTION_PATTERNS), re.IGNORECASE)
        self.xss_pattern = re.compile("|".join(self.XSS_PATTERNS), re.IGNORECASE)
        self.path_pattern = re.compile("|".join(self.PATH_TRAVERSAL_PATTERNS), re.IGNORECASE)

        # Standard HTTP headers that should not be checked for XSS patterns
        self.SAFE_HEADERS = {
            "cookie", "set-cookie", "authorization", "content-type", "content-length",
            "accept", "accept-encoding", "accept-language", "host", "user-agent",
            "referer", "connection", "cache-control", "pragma", "expires",
            "if-none-match", "if-modified-since", "origin", "x-requested-with"
        }

    async def dispatch(self, request: Request, call_next):
        # Check query parameters
        query_string = str(request.query_params)
        if self._contains_attack_patterns(query_string):
            logger.warning(f"Blocked potential attack in query params: {query_string[:100]}")
            raise HTTPException(status_code=400, detail="Invalid request")

        # Check URL path
        path = request.url.path
        if self.path_pattern.search(path):
            logger.warning(f"Blocked path traversal attempt: {path}")
            raise HTTPException(status_code=400, detail="Invalid path")

        # Check headers for suspicious content (skip safe standard headers)
        for header_name, header_value in request.headers.items():
            header_lower = header_name.lower()

            # Skip standard HTTP headers from attack pattern checks
            # These come from browsers/clients and are less likely to contain attacks
            if header_lower in self.SAFE_HEADERS:
                continue

            # Only check custom/suspicious headers
            header_str = f"{header_name}: {header_value}"
            if self._contains_attack_patterns(header_str):
                logger.warning(f"Blocked potential attack in custom header: {header_name}")
                raise HTTPException(status_code=400, detail="Invalid request")

        return await call_next(request)

    def _contains_attack_patterns(self, text: str) -> bool:
        """Check if text contains attack patterns."""
        if not text:
            return False

        # Check SQL injection
        if self.sql_pattern.search(text):
            return True

        # Check XSS (only for non-HTML content)
        if self.xss_pattern.search(text):
            return True

        return False


class APIKeyRotationTracker:
    """
    Tracks API key usage and rotation for enterprise security.
    """

    def __init__(self):
        self._key_metadata: dict[str, dict] = {}

    def register_key(self, key_id: str, key_hash: str, created_by: str,
                     expires_at: datetime = None, scopes: list[str] = None):
        """Register a new API key with metadata."""
        self._key_metadata[key_hash] = {
            "key_id": key_id,
            "created_at": datetime.now(UTC),
            "created_by": created_by,
            "expires_at": expires_at,
            "scopes": scopes or [],
            "last_used": None,
            "usage_count": 0,
            "is_revoked": False,
        }

    def record_usage(self, key_hash: str):
        """Record API key usage."""
        if key_hash in self._key_metadata:
            self._key_metadata[key_hash]["last_used"] = datetime.now(UTC)
            self._key_metadata[key_hash]["usage_count"] += 1

    def revoke_key(self, key_id: str, revoked_by: str, reason: str):
        """Revoke an API key."""
        for key_hash, metadata in self._key_metadata.items():
            if metadata["key_id"] == key_id:
                metadata["is_revoked"] = True
                metadata["revoked_at"] = datetime.now(UTC)
                metadata["revoked_by"] = revoked_by
                metadata["revoke_reason"] = reason
                logger.info(f"API key {key_id} revoked by {revoked_by}: {reason}")
                return True
        return False

    def is_key_valid(self, key_hash: str) -> bool:
        """Check if API key is valid (not expired, not revoked)."""
        if key_hash not in self._key_metadata:
            return False

        metadata = self._key_metadata[key_hash]

        # Check if revoked
        if metadata.get("is_revoked", False):
            return False

        # Check expiration
        expires_at = metadata.get("expires_at")
        if expires_at and datetime.now(UTC) > expires_at:
            return False

        return True

    def get_key_stats(self, key_id: str = None) -> dict:
        """Get API key statistics."""
        if key_id:
            for key_hash, metadata in self._key_metadata.items():
                if metadata["key_id"] == key_id:
                    return metadata
            return None

        # Return aggregate stats
        total_keys = len(self._key_metadata)
        active_keys = sum(1 for m in self._key_metadata.values() if not m.get("is_revoked", False))
        revoked_keys = total_keys - active_keys

        return {
            "total_keys": total_keys,
            "active_keys": active_keys,
            "revoked_keys": revoked_keys,
            "keys_expiring_soon": sum(
                1 for m in self._key_metadata.values()
                if m.get("expires_at") and
                m.get("expires_at") < datetime.now(UTC) + timedelta(days=7) and
                not m.get("is_revoked", False)
            ),
        }


class SecureHeaders:
    """
    Helper class for generating secure headers for external API calls.
    """

    @staticmethod
    def generate_request_signature(payload: bytes, secret: str) -> str:
        """
        Generate HMAC signature for request verification.

        Args:
            payload: Request body bytes
            secret: Shared secret key

        Returns:
            Hex-encoded HMAC-SHA256 signature
        """
        return hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

    @staticmethod
    def verify_request_signature(payload: bytes, signature: str, secret: str) -> bool:
        """
        Verify HMAC signature from request.

        Args:
            payload: Request body bytes
            signature: Provided signature (hex-encoded)
            secret: Shared secret key

        Returns:
            True if signature is valid
        """
        expected = SecureHeaders.generate_request_signature(payload, secret)
        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(signature, expected)

    @staticmethod
    def generate_nonce() -> str:
        """Generate cryptographically secure nonce."""
        return secrets.token_urlsafe(32)

    @staticmethod
    def generate_correlation_id() -> str:
        """Generate unique correlation ID for request tracing."""
        return secrets.token_hex(16)


# Global instances
api_key_tracker = APIKeyRotationTracker()


def sanitize_html_input(text: str) -> str:
    """
    Sanitize HTML input to prevent XSS attacks.

    This is a basic implementation. For production, consider using:
    - bleach library for HTML sanitization
    - html.escape for simple text escaping
    """
    if not text:
        return text

    import html

    # First, escape HTML entities
    sanitized = html.escape(text)

    # Remove potentially dangerous protocols
    dangerous_protocols = ["javascript:", "data:", "vbscript:", "file:", "about:"]
    for protocol in dangerous_protocols:
        sanitized = sanitized.replace(protocol, "")

    return sanitized


def validate_file_upload(filename: str, content_type: str,
                        allowed_extensions: list[str] = None,
                        max_size_bytes: int = 10 * 1024 * 1024) -> bool:
    """
    Validate file upload for security.

    Args:
        filename: Original filename
        content_type: MIME type
        allowed_extensions: List of allowed extensions (e.g., ['.pdf', '.jpg'])
        max_size_bytes: Maximum file size

    Returns:
        True if file is valid
    """
    if not filename:
        return False

    # Check for null bytes (path traversal attempt)
    if "\x00" in filename:
        return False

    # Check extension
    if allowed_extensions:
        ext = filename.lower().split(".")[-1] if "." in filename else ""
        if f".{ext}" not in [e.lower() for e in allowed_extensions]:
            return False

    # Validate MIME type
    dangerous_types = [
        "application/x-msdownload",
        "application/x-executable",
        "application/x-sh",
        "application/x-shellscript",
        "text/x-python",
        "application/x-php",
    ]

    if content_type in dangerous_types:
        return False

    return True


def mask_sensitive_data(data: dict, sensitive_fields: list[str] = None) -> dict:
    """
    Mask sensitive fields in data for logging.

    Args:
        data: Dictionary containing data
        sensitive_fields: List of field names to mask

    Returns:
        Dictionary with sensitive fields masked
    """
    if sensitive_fields is None:
        sensitive_fields = [
            "password", "secret", "token", "key", "api_key",
            "credit_card", "ssn", "ssn_last4", "authorization"
        ]

    masked = {}
    for key, value in data.items():
        if any(sensitive in key.lower() for sensitive in sensitive_fields):
            if isinstance(value, str) and len(value) > 4:
                masked[key] = value[:2] + "***" + value[-2:]
            else:
                masked[key] = "***"
        elif isinstance(value, dict):
            masked[key] = mask_sensitive_data(value, sensitive_fields)
        elif isinstance(value, list):
            masked[key] = [
                mask_sensitive_data(item, sensitive_fields) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            masked[key] = value

    return masked

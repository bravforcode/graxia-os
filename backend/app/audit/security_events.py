"""Security audit helpers with redaction-safe payload handling."""
from __future__ import annotations

import hashlib
import logging
from collections.abc import Mapping
from typing import Any

from fastapi import Request

from app.auth.context import AuthContext
from app.core.request_context import get_correlation_id, get_request_id
from app.services.audit_service import log_audit_event

logger = logging.getLogger(__name__)

_SENSITIVE_KEYS = (
    "authorization",
    "password",
    "secret",
    "token",
    "cookie",
    "api_key",
    "access_token",
    "refresh_token",
)


def fingerprint_token(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


_UNMATCHED_ROUTE_LABEL = "unmatched"
_DELIVERY_CAPABILITY_PATH = "/api/v1/funnel/delivery/"


def safe_path_for_logging(path: str) -> str:
    """Redact delivery capability paths while retaining ordinary diagnostics."""
    marker_index = path.find(_DELIVERY_CAPABILITY_PATH)
    if marker_index < 0 or (marker_index > 0 and path[marker_index - 1] != "/"):
        return path

    prefix_end = marker_index + len(_DELIVERY_CAPABILITY_PATH)
    prefix = path[:prefix_end]
    tail = path[prefix_end:]
    action = next(
        (suffix for suffix in ("/consume", "/download") if tail.endswith(suffix)),
        "",
    )
    return f"{prefix}[REDACTED]{action}"


def _delivery_route_template(path: str) -> str | None:
    marker_index = path.find(_DELIVERY_CAPABILITY_PATH)
    if marker_index < 0 or (marker_index > 0 and path[marker_index - 1] != "/"):
        return None

    tail = path[marker_index + len(_DELIVERY_CAPABILITY_PATH) :]
    if not tail:
        return None
    action = next(
        (suffix for suffix in ("/consume", "/download") if tail.endswith(suffix)),
        "",
    )
    token_path = tail[: -len(action)] if action else tail
    if not token_path.strip("/"):
        return None
    return f"{_DELIVERY_CAPABILITY_PATH}{{token}}{action}"


def safe_request_path(request: Request) -> str:
    """Return a route template, canonicalizing delivery paths before routing."""
    route_path = getattr(request.scope.get("route"), "path", None)
    if isinstance(route_path, str) and route_path.startswith("/"):
        return _delivery_route_template(route_path) or safe_path_for_logging(route_path)
    return _delivery_route_template(request.url.path) or _UNMATCHED_ROUTE_LABEL


def safe_route_or_tool(request: Request, route_or_tool: str | None) -> str:
    """Preserve safe static tool names without accepting raw URL paths."""
    if route_or_tool and not any(
        separator in route_or_tool for separator in ("/", "\\", "?", "#")
    ):
        return route_or_tool
    return safe_request_path(request)


def redact_security_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in (payload or {}).items():
        lowered = key.lower()
        if any(s in lowered for s in _SENSITIVE_KEYS):
            redacted[key] = "[REDACTED]"
        elif isinstance(value, Mapping):
            redacted[key] = redact_security_payload(value)
        else:
            redacted[key] = value
    return redacted


async def emit_security_event(
    request: Request,
    *,
    event_type: str,
    reason_code: str,
    decision: str,
    route_or_tool: str | None = None,
    risk_level: str = "APPROVAL_REQUIRED",
    redacted_payload: Mapping[str, Any] | None = None,
) -> None:
    auth: AuthContext | None = getattr(request.state, "auth_context", None)
    try:
        await log_audit_event(
            app=request.app,
            action=f"security.{event_type}",
            event_type=event_type,
            event_category="security",
            severity="WARNING" if decision == "blocked" else "ERROR",
            outcome=decision,
            success=False,
            metadata={
                "reason_code": reason_code,
                "risk_level": risk_level,
                "route_or_tool": safe_route_or_tool(request, route_or_tool),
                "request_id": get_request_id(request),
                "correlation_id": get_correlation_id(request),
                "organization_id": str(auth.organization_id) if auth and auth.organization_id else None,
                "actor_type": auth.actor_type if auth else "anonymous",
                "actor_id": auth.actor_id if auth else None,
                "payload": redact_security_payload(redacted_payload),
            },
            user_id=auth.actor_id if auth and auth.actor_type in {"user", "admin"} else None,
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent"),
            request_path=safe_request_path(request),
            request_method=request.method,
            error_message=reason_code,
        )
    except Exception:
        logger.warning("Failed to emit security audit event: %s", event_type, exc_info=True)


async def emit_security_event_from_context(
    request: Request,
    *,
    event_type: str,
    reason_code: str,
    decision: str,
    route_or_tool: str | None = None,
    risk_level: str = "LOW_WRITE",
    redacted_payload: Mapping[str, Any] | None = None,
) -> None:
    """Emit a security event from an MCP context where actor info is explicit."""
    try:
        await log_audit_event(
            app=request.app,
            action=f"security.{event_type}",
            event_type=event_type,
            event_category="security",
            severity="WARNING" if decision == "blocked" else "ERROR",
            outcome=decision,
            success=False,
            metadata={
                "reason_code": reason_code,
                "risk_level": risk_level,
                "route_or_tool": safe_route_or_tool(request, route_or_tool),
                "request_id": get_request_id(request),
                "correlation_id": get_correlation_id(request),
                "payload": redact_security_payload(redacted_payload),
            },
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent"),
            request_path=safe_request_path(request),
            request_method=request.method,
            error_message=reason_code,
        )
    except Exception:
        logger.warning("Failed to emit context security audit event: %s", event_type, exc_info=True)

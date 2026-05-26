"""Centralized safe exception handlers."""
from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError

from app.audit.security_events import emit_security_event
from app.core.errors import AppError, build_error_response

logger = logging.getLogger(__name__)


def _map_http_exception(exc: HTTPException) -> tuple[str, str]:
    detail = str(exc.detail or "").lower()
    if exc.status_code == 401:
        return ("AUTH_INVALID" if "invalid" in detail else "AUTH_REQUIRED", "Authentication required")
    if exc.status_code == 403:
        if "dangerous" in detail:
            return "DANGEROUS_BLOCKED", "Dangerous action is blocked"
        if "approval" in detail:
            return "APPROVAL_REQUIRED", "Human approval is required before this action can continue"
        return "PERMISSION_DENIED", "Not authorized to access this resource"
    if exc.status_code == 404:
        return "NOT_FOUND", "Resource not found"
    if exc.status_code == 413:
        return "PAYLOAD_TOO_LARGE", "Request payload is too large"
    if exc.status_code == 429:
        return "RATE_LIMITED", "Too many requests"
    if exc.status_code == 422:
        return "VALIDATION_ERROR", "Request validation failed"
    return "INTERNAL_ERROR", "Internal server error"


async def _emit_safe_error_audit(request: Request, code: str, message: str, status_code: int) -> None:
    event_type = {
        "AUTH_REQUIRED": "auth.missing",
        "AUTH_INVALID": "auth.invalid",
        "PERMISSION_DENIED": "permission.denied",
        "ORG_REQUIRED": "org.required",
        "ORG_FORBIDDEN": "org.boundary.denied",
        "RATE_LIMITED": "rate_limit.exceeded",
        "PAYLOAD_TOO_LARGE": "payload.too_large",
        "DANGEROUS_BLOCKED": "mcp.dangerous.blocked",
    }.get(code, "safe_error.emitted")
    await emit_security_event(
        request,
        event_type=event_type,
        reason_code=code,
        decision="blocked" if status_code < 500 else "error",
        route_or_tool=request.url.path,
        redacted_payload={"status_code": status_code, "message": message},
    )


async def handle_app_error(request: Request, exc: AppError):
    await _emit_safe_error_audit(request, exc.code, exc.message, exc.status_code)
    return build_error_response(
        request,
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        headers=exc.headers,
    )


async def handle_http_exception(request: Request, exc: HTTPException):
    code, message = _map_http_exception(exc)
    await _emit_safe_error_audit(request, code, message, exc.status_code)
    return build_error_response(
        request,
        code=code,
        message=message,
        status_code=exc.status_code,
        headers=exc.headers,
    )


async def handle_validation_exception(request: Request, exc: RequestValidationError):
    await _emit_safe_error_audit(request, "VALIDATION_ERROR", "Request validation failed", 422)
    return build_error_response(
        request,
        code="VALIDATION_ERROR",
        message="Request validation failed",
        status_code=422,
    )


async def handle_permission_error(request: Request, exc: PermissionError):
    await _emit_safe_error_audit(request, "NOT_FOUND", "Resource not found", 404)
    return build_error_response(
        request,
        code="NOT_FOUND",
        message="Resource not found",
        status_code=404,
    )


async def handle_unhandled_exception(request: Request, exc: Exception):
    logger.exception("Unhandled request error", exc_info=exc)
    await _emit_safe_error_audit(request, "INTERNAL_ERROR", "Internal server error", 500)
    return build_error_response(
        request,
        code="INTERNAL_ERROR",
        message="Internal server error",
        status_code=500,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(HTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_validation_exception)
    app.add_exception_handler(PermissionError, handle_permission_error)
    app.add_exception_handler(Exception, handle_unhandled_exception)

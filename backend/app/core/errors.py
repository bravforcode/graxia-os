"""Safe external error contract for API responses."""
from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.request_context import get_correlation_id, get_request_id


@dataclass(slots=True)
class AppError(Exception):
    code: str
    message: str
    status_code: int
    headers: dict[str, str] = field(default_factory=dict)


class AuthRequiredError(AppError):
    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__("AUTH_REQUIRED", message, 401)


class AuthInvalidError(AppError):
    def __init__(self, message: str = "Authentication is invalid") -> None:
        super().__init__("AUTH_INVALID", message, 401)


class PermissionDeniedError(AppError):
    def __init__(self, message: str = "Not authorized to access this resource") -> None:
        super().__init__("PERMISSION_DENIED", message, 403)


class OrgRequiredError(AppError):
    def __init__(self, message: str = "Organization context is required") -> None:
        super().__init__("ORG_REQUIRED", message, 401)


class OrgForbiddenError(AppError):
    def __init__(self, message: str = "Not authorized to access this resource") -> None:
        super().__init__("ORG_FORBIDDEN", message, 403)


class RateLimitedError(AppError):
    def __init__(self, retry_after_seconds: int | None = None) -> None:
        headers: dict[str, str] = {}
        if retry_after_seconds is not None:
            headers["Retry-After"] = str(retry_after_seconds)
        super().__init__("RATE_LIMITED", "Too many requests", 429, headers)


class PayloadTooLargeError(AppError):
    def __init__(self) -> None:
        super().__init__("PAYLOAD_TOO_LARGE", "Request payload is too large", 413)


class DangerousBlockedError(AppError):
    def __init__(self, message: str = "Dangerous action is blocked") -> None:
        super().__init__("DANGEROUS_BLOCKED", message, 403)


class ApprovalRequiredError(AppError):
    def __init__(self, message: str = "Human approval is required before this action can continue") -> None:
        super().__init__("APPROVAL_REQUIRED", message, 403)


def build_error_body(request: Request, code: str, message: str) -> dict[str, object]:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": get_request_id(request),
            "correlation_id": get_correlation_id(request),
        }
    }


def build_error_response(
    request: Request,
    *,
    code: str,
    message: str,
    status_code: int,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    response = JSONResponse(
        build_error_body(request, code, message),
        status_code=status_code,
        headers=headers or {},
    )
    response.headers.setdefault("X-Request-ID", get_request_id(request))
    response.headers.setdefault("X-Correlation-ID", get_correlation_id(request))
    return response

"""Request/correlation context helpers and middleware."""
from __future__ import annotations

from collections.abc import Callable, Awaitable
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


def ensure_request_id(request: Request) -> str:
    request_id = (
        request.headers.get("X-Graxia-Request-Id", "").strip()
        or request.headers.get("X-Request-ID", "").strip()
        or getattr(request.state, "request_id", None)
    )
    if request_id:
        request.state.request_id = request_id
        return request_id
    request_id = f"req_{uuid4().hex}"
    request.state.request_id = request_id
    return request_id


def ensure_correlation_id(request: Request) -> str:
    correlation_id = (
        request.headers.get("X-Correlation-ID", "").strip()
        or request.headers.get("X-Graxia-Correlation-Id", "").strip()
        or getattr(request.state, "correlation_id", None)
        or ensure_request_id(request)
    )
    request.state.correlation_id = correlation_id
    return correlation_id


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or ensure_request_id(request)


def get_correlation_id(request: Request) -> str:
    return getattr(request.state, "correlation_id", None) or ensure_correlation_id(request)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Ensures request and correlation IDs exist for all downstream layers."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]):
        request_id = ensure_request_id(request)
        correlation_id = ensure_correlation_id(request)
        response = await call_next(request)
        response.headers.setdefault("X-Request-ID", request_id)
        response.headers.setdefault("X-Correlation-ID", correlation_id)
        return response

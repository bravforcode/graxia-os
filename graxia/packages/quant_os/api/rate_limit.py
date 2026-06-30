"""
In-memory sliding-window rate limiter for FastAPI.

Middleware extracts client IP (X-Forwarded-For if behind proxy),
matches request path against configurable limits, and returns
429 + Retry-After when a bucket is exhausted.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse


# ── bucket ─────────────────────────────────────────────────────────────
@dataclass
class _Bucket:
    max_requests: int
    window_seconds: int
    _timestamps: list[float] = field(default_factory=list, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def allow(self) -> bool:
        with self._lock:
            now = time.time()
            cutoff = now - self.window_seconds
            self._timestamps = [t for t in self._timestamps if t > cutoff]
            if len(self._timestamps) >= self.max_requests:
                return False
            self._timestamps.append(now)
            return True

    def retry_after(self) -> float:
        with self._lock:
            if not self._timestamps:
                return 0.0
            return max(0.0, self._timestamps[0] + self.window_seconds - time.time())


# ── rule table ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RateLimitRule:
    path_prefix: str
    max_requests: int
    window_seconds: int = 60
    methods: tuple[str, ...] = ("GET", "POST", "PUT", "DELETE", "PATCH")


DEFAULT_RULES: list[RateLimitRule] = [
    RateLimitRule("/api/signal",    max_requests=10, methods=("POST",)),
    RateLimitRule("/api/webhook",   max_requests=20, methods=("POST",)),
    RateLimitRule("/api/orders",    max_requests=30, methods=("GET", "POST")),
    RateLimitRule("/api/positions", max_requests=30, methods=("GET",)),
    RateLimitRule("/api/risk",      max_requests=30, methods=("GET",)),
]


# ── middleware ──────────────────────────────────────────────────────────
class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP, per-path-prefix sliding-window rate limiter."""

    def __init__(self, app, rules: list[RateLimitRule] | None = None):
        super().__init__(app)
        self.rules = rules or DEFAULT_RULES
        self._buckets: dict[tuple[str, str, str], _Bucket] = {}
        self._lock = threading.Lock()

    def _get_bucket(self, key: tuple[str, str, str], max_req: int, window: int) -> _Bucket:
        if key not in self._buckets:
            with self._lock:
                if key not in self._buckets:
                    self._buckets[key] = _Bucket(max_requests=max_req, window_seconds=window)
        return self._buckets[key]

    @staticmethod
    def _client_ip(request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path
        method = request.method.upper()
        ip = self._client_ip(request)

        for rule in self.rules:
            if path.startswith(rule.path_prefix) and method in rule.methods:
                key = (rule.path_prefix, method, ip)
                bucket = self._get_bucket(key, rule.max_requests, rule.window_seconds)
                if not bucket.allow():
                    retry = int(bucket.retry_after()) + 1
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Too Many Requests"},
                        headers={"Retry-After": str(retry)},
                    )
                break

        return await call_next(request)


# ── public helper for standalone use (e.g. signal_service) ────────────
class InMemoryRateLimiter:
    """Drop-in replacement for _RateLimiter in signal_service."""

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self._bucket = _Bucket(max_requests=max_requests, window_seconds=window_seconds)

    def allow(self, client_id: str = "default") -> bool:
        return self._bucket.allow()

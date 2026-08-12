"""
Sliding-window rate limiter for FastAPI with Redis backing.

Uses Redis for cross-worker/cross-container rate limiting when available,
falls back to in-memory per-process buckets otherwise.

Middleware extracts client IP (X-Forwarded-For if behind proxy),
matches request path against configurable limits, and returns
429 + Retry-After when a bucket is exhausted.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse


# ── Redis backend ──────────────────────────────────────────────────────
class _RedisBackend:
    """Async Redis sliding-window counter. Shared across workers/containers."""

    def __init__(self, url: str):
        import redis.asyncio as aioredis

        self._pool = aioredis.ConnectionPool.from_url(url, decode_responses=True)
        self._client = aioredis.Redis(connection_pool=self._pool)

    async def allow(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """Sliding window using sorted sets. O(log N) per check."""
        now = time.time()
        pipe = self._client.pipeline()
        # Remove expired entries
        pipe.zremrangebyscore(key, 0, now - window_seconds)
        # Count current window
        pipe.zcard(key)
        # Add current request if allowed
        pipe.zadd(key, {str(now): now})
        # Set TTL
        pipe.expire(key, window_seconds + 1)
        results = await pipe.execute()
        count = results[1]  # zcard result
        # If we were over limit, remove the optimistically added entry
        if count >= max_requests:
            await self._client.zrem(key, str(now))
            return False
        return True

    async def retry_after(self, key: str, window_seconds: int) -> float:
        """Return seconds until the oldest entry in the window expires."""
        members = await self._client.zrange(key, 0, 0, withscores=True)
        if not members:
            return 0.0
        oldest = members[0][1]
        return max(0.0, oldest + window_seconds - time.time())

    async def close(self):
        await self._client.close()
        await self._pool.aclose()


# ── In-memory backend ──────────────────────────────────────────────────
class _InMemoryBackend:
    """Per-process sliding-window counter. No cross-worker sharing."""

    def __init__(self):
        self._buckets: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow_sync(self, key: str, max_requests: int, window_seconds: int) -> bool:
        with self._lock:
            now = time.time()
            cutoff = now - window_seconds
            ts = self._buckets.get(key, [])
            ts = [t for t in ts if t > cutoff]
            if len(ts) >= max_requests:
                self._buckets[key] = ts
                return False
            ts.append(now)
            self._buckets[key] = ts
            return True

    def retry_after_sync(self, key: str, window_seconds: int) -> float:
        with self._lock:
            ts = self._buckets.get(key, [])
            if not ts:
                return 0.0
            return max(0.0, ts[0] + window_seconds - time.time())


# backward-compatible wrapper for tests (single-key bucket)
class _Bucket:
    """Single-key sliding window — wraps _InMemoryBackend for test compat."""

    def __init__(self, max_requests: int, window_seconds: int):
        self._be = _InMemoryBackend()
        self._max = max_requests
        self._win = window_seconds
        self._key = "test"

    def allow(self) -> bool:
        return self._be.allow_sync(self._key, self._max, self._win)

    def retry_after(self) -> float:
        return self._be.retry_after_sync(self._key, self._win)

    @property
    def _timestamps(self):
        return self._be._buckets.get(self._key, [])

    @_timestamps.setter
    def _timestamps(self, val):
        self._be._buckets[self._key] = val


# ── Factory ────────────────────────────────────────────────────────────
_backend = None
_backend_lock = threading.Lock()


def _get_backend():
    global _backend
    if _backend is not None:
        return _backend
    with _backend_lock:
        if _backend is not None:
            return _backend
        redis_url = os.getenv("REDIS_URL", "").strip()
        if redis_url:
            try:
                _backend = _RedisBackend(redis_url)
                return _backend
            except Exception:
                pass
        _backend = _InMemoryBackend()
        return _backend


def _reset_backend():
    """Reset backend singleton — use in tests only."""
    global _backend
    _backend = None


# ── Rule table ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RateLimitRule:
    path_prefix: str
    max_requests: int
    window_seconds: int = 60
    methods: tuple[str, ...] = ("GET", "POST", "PUT", "DELETE", "PATCH")


DEFAULT_RULES: list[RateLimitRule] = [
    RateLimitRule("/api/signal", max_requests=10, methods=("POST",)),
    RateLimitRule("/api/webhook", max_requests=20, methods=("POST",)),
    RateLimitRule("/api/orders", max_requests=30, methods=("GET", "POST")),
    RateLimitRule("/api/positions", max_requests=30, methods=("GET",)),
    RateLimitRule("/api/risk", max_requests=30, methods=("GET",)),
]


# ── Middleware ──────────────────────────────────────────────────────────
class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP, per-path-prefix sliding-window rate limiter.
    Uses Redis when REDIS_URL is set, otherwise in-memory.
    """

    def __init__(self, app, rules: list[RateLimitRule] | None = None):
        super().__init__(app)
        self.rules = rules or DEFAULT_RULES

    @staticmethod
    def _client_ip(request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        method = request.method.upper()
        ip = self._client_ip(request)

        for rule in self.rules:
            if path.startswith(rule.path_prefix) and method in rule.methods:
                key = f"rl:{rule.path_prefix}:{method}:{ip}"
                backend = _get_backend()

                if isinstance(backend, _RedisBackend):
                    allowed = await backend.allow(key, rule.max_requests, rule.window_seconds)
                    if not allowed:
                        retry = int(await backend.retry_after(key, rule.window_seconds)) + 1
                        return JSONResponse(
                            status_code=429,
                            content={"detail": "Too Many Requests"},
                            headers={"Retry-After": str(retry)},
                        )
                else:
                    if not backend.allow_sync(key, rule.max_requests, rule.window_seconds):
                        retry = int(backend.retry_after_sync(key, rule.window_seconds)) + 1
                        return JSONResponse(
                            status_code=429,
                            content={"detail": "Too Many Requests"},
                            headers={"Retry-After": str(retry)},
                        )
                break

        return await call_next(request)


# ── Standalone helper (e.g. signal_service) ────────────────────────────
class InMemoryRateLimiter:
    """Drop-in replacement for _RateLimiter in signal_service."""

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self._backend = _InMemoryBackend()
        self._max = max_requests
        self._window = window_seconds

    def allow(self, client_id: str = "default") -> bool:
        return self._backend.allow_sync(client_id, self._max, self._window)

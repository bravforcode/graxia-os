"""
graxia/services/revenue_os_api/middleware.py
Security headers and rate limiting middleware — fixes HIGH-05.

RateLimiter:
  - Sliding window with probabilistic cleanup (no unbounded memory growth)
  - asyncio.Lock scoped to IP only (not global) for high throughput
  - Production: swap for Redis-backed slowapi (see comment at bottom)
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from collections import defaultdict, deque
from typing import Dict
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

_HSTS_MAX_AGE = 31_536_000  # 1 year
_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "frame-ancestors 'none';"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Injects a unique X-Request-ID and all production security headers.
    Strips server fingerprint headers.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid4())
        request.state.request_id = request_id

        start = time.monotonic()
        response: Response = await call_next(request)
        duration_ms = (time.monotonic() - start) * 1000

        response.headers.update({
            "X-Request-ID": request_id,
            "X-Response-Time": f"{duration_ms:.1f}ms",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Strict-Transport-Security": f"max-age={_HSTS_MAX_AGE}; includeSubDomains; preload",
            "Content-Security-Policy": _CSP,
            "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        })
        # Remove server fingerprint
        response.headers.pop("Server", None)
        response.headers.pop("X-Powered-By", None)

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding window per-IP rate limiter with memory-safe cleanup.

    For multi-process / multi-instance deploys, replace with:
        from slowapi import Limiter
        from slowapi.util import get_remote_address
        limiter = Limiter(key_func=get_remote_address, storage_uri=REDIS_URL)

    Cleanup strategy:
      - On 1% of requests, sweep IPs with no activity in last 5 minutes
      - Per-IP asyncio.Lock (not a global lock) — O(1) contention per client
    """

    _EXEMPT_PATHS = frozenset({"/api/system/readiness", "/api/system/metrics"})

    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        burst: int = 20,
    ) -> None:
        super().__init__(app)
        self._rpm = requests_per_minute
        self._burst = burst
        self._windows: Dict[str, deque] = defaultdict(deque)
        self._locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in self._EXEMPT_PATHS:
            return await call_next(request)

        client_ip = (request.client.host if request.client else "unknown")
        now = time.time()
        window_start = now - 60.0

        async with self._locks[client_ip]:
            window = self._windows[client_ip]
            # Slide the window: remove timestamps older than 60s
            while window and window[0] < window_start:
                window.popleft()

            if len(window) >= self._rpm + self._burst:
                logger.warning("Rate limit exceeded for IP: %s", client_ip)
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too Many Requests — rate limit exceeded"},
                    headers={"Retry-After": "60"},
                )
            window.append(now)

        # Probabilistic cleanup: 1% of requests → sweep stale IPs
        if random.random() < 0.01:
            stale_cutoff = now - 300  # 5 minutes of inactivity
            stale_ips = [
                ip for ip, w in list(self._windows.items())
                if not w or w[-1] < stale_cutoff
            ]
            for ip in stale_ips:
                self._windows.pop(ip, None)
                self._locks.pop(ip, None)

        return await call_next(request)

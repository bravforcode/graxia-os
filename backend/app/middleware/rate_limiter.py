"""
Rate Limiting Middleware
Production rate limiting for GRAXIA OS API
"""

import hashlib
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimiter:
    """Token bucket rate limiter"""

    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.clients: dict[str, tuple[list, float]] = {}

    def is_allowed(self, client_id: str) -> tuple[bool, int, int]:
        """Check if request is allowed"""
        now = time.time()

        if client_id not in self.clients:
            self.clients[client_id] = ([now], now)
            return True, self.max_requests - 1, self.window_seconds

        requests, window_start = self.clients[client_id]

        # Reset if window expired
        if now - window_start > self.window_seconds:
            self.clients[client_id] = ([now], now)
            return True, self.max_requests - 1, self.window_seconds

        # Clean old requests
        requests = [r for r in requests if now - r <= self.window_seconds]

        # Check limit
        if len(requests) >= self.max_requests:
            retry_after = int(self.window_seconds - (now - window_start))
            return False, 0, retry_after

        requests.append(now)
        self.clients[client_id] = (requests, window_start)

        remaining = self.max_requests - len(requests)
        reset_time = int(window_start + self.window_seconds - now)
        return True, remaining, reset_time


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware for API endpoints"""

    def __init__(self, app, default_limit: int = 100, window: int = 60):
        super().__init__(app)
        self.limiter = RateLimiter(default_limit, window)
        self.endpoint_limits = {
            "/api/v1/embeddings": (50, 60),  # Stricter for expensive ops
            "/api/v1/knowledge/search": (200, 60),
        }

    async def dispatch(self, request: Request, call_next):
        # Get client identifier
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "")
        client_id = hashlib.sha256(f"{client_ip}:{user_agent}".encode()).hexdigest()[:16]

        # Check endpoint-specific limits
        path = request.url.path
        limit, window = self.endpoint_limits.get(path, (100, 60))

        # Temporarily set limit
        old_limit = self.limiter.max_requests
        self.limiter.max_requests = limit

        allowed, remaining, reset = self.limiter.is_allowed(client_id)
        self.limiter.max_requests = old_limit

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded", "retry_after": reset},
                headers={
                    "Retry-After": str(reset),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset),
                },
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset)

        return response

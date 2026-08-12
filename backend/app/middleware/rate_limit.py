"""Sliding-window rate limiting middleware with Redis and test fallback."""
from __future__ import annotations

import hashlib
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

from app.audit.security_events import emit_security_event, fingerprint_token
from app.config import settings
from app.core.auth import decode_access_token, extract_bearer_token
from app.core.errors import build_error_response
from app.core.monitoring import metrics_collector
from app.core.request_context import get_correlation_id, get_request_id
from app.services.audit_service import log_audit_event
from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

_memory_rate_limits: dict[str, list[float]] = defaultdict(list)


def reset_rate_limit_state() -> None:
    _memory_rate_limits.clear()


@dataclass(frozen=True)
class RateLimitRule:
    name: str
    limit: int
    window_seconds: int


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Redis-backed sliding window rules for auth, public, and control-plane traffic."""

    HEALTH_RULE = RateLimitRule("health", 120, 60)
    LOGIN_RULE = RateLimitRule("login", 10, 60)
    REGISTER_RULE = RateLimitRule("register", 5, 60)
    REFRESH_RULE = RateLimitRule("refresh", 30, 60)
    ADMIN_RULE = RateLimitRule("admin", 600, 60)
    API_READ_RULE = RateLimitRule("api_read", 300, 60)
    API_WRITE_RULE = RateLimitRule("api_write", 100, 60)
    MCP_RULE = RateLimitRule("mcp", 120, 60)
    WORKFLOW_RULE = RateLimitRule("workflow", 30, 60)
    LEAD_CAPTURE_RULE = RateLimitRule("lead_capture", 20, 60)
    CHECKOUT_RULE = RateLimitRule("checkout", 20, 60)
    DELIVERY_RULE = RateLimitRule("delivery", 30, 60)

    async def dispatch(self, request: Request, call_next: Callable):
        if request.url.path == "/health":
            return await call_next(request)

        redis_client = getattr(request.app.state, "redis", None)
        rule = self._resolve_rule(request)
        if rule is None:
            return await call_next(request)

        identifier = self._resolve_identifier(request, rule.name)
        try:
            remaining, retry_after = await self._check_rate_limit(
                redis_client,
                rule,
                identifier,
                request.method,
                request.url.path,
            )
        except HTTPException as exc:
            metrics_collector.record_rate_limit(rule.name)
            await emit_security_event(
                request,
                event_type="rate_limit.exceeded",
                reason_code="RATE_LIMITED",
                decision="blocked",
                route_or_tool=request.url.path,
                risk_level="LOW_WRITE",
                redacted_payload={"rule": rule.name, "identifier": identifier},
            )
            await log_audit_event(
                app=request.app,
                action="security.rate_limit",
                event_type="rate_limit_exceeded",
                event_category="security",
                severity="WARNING",
                outcome="blocked",
                success=False,
                metadata={"rule": rule.name, "identifier": identifier},
                ip_address=request.client.host if request.client else "unknown",
                user_agent=request.headers.get("user-agent"),
                request_path=request.url.path,
                request_method=request.method,
            )
            return build_error_response(
                request,
                code="RATE_LIMITED",
                message="Too many requests",
                status_code=exc.status_code,
                headers=exc.headers or {},
            )

        response = await call_next(request)
        response.headers.setdefault("X-Request-ID", get_request_id(request))
        response.headers.setdefault("X-Correlation-ID", get_correlation_id(request))
        response.headers["RateLimit-Limit"] = str(rule.limit)
        response.headers["RateLimit-Remaining"] = str(max(remaining, 0))
        response.headers["RateLimit-Reset"] = str(rule.window_seconds)
        if retry_after is not None:
            response.headers["Retry-After"] = str(retry_after)
        return response

    def _resolve_rule(self, request: Request) -> RateLimitRule | None:
        path = request.url.path
        if path.startswith("/api/v1/health"):
            return self.HEALTH_RULE
        if path == "/api/v1/auth/login" and request.method == "POST":
            return self.LOGIN_RULE
        if path == "/api/v1/auth/register" and request.method == "POST":
            return self.REGISTER_RULE
        if path == "/api/v1/auth/refresh" and request.method == "POST":
            return self.REFRESH_RULE
        if path.startswith("/api/v1/funnel/lead-magnets/") and path.endswith("/capture") and request.method == "POST":
            return self.LEAD_CAPTURE_RULE
        if path.startswith("/api/v1/billing/checkout") and request.method == "POST":
            return self.CHECKOUT_RULE
        if path.startswith("/api/v1/funnel/delivery/") and request.method == "GET":
            return self.DELIVERY_RULE
        if path.startswith("/api/v1/mcp") and request.method == "POST":
            return self.MCP_RULE
        if path.startswith("/api/v1/workflows") and request.method == "POST":
            return self.WORKFLOW_RULE
        if path.startswith("/api/v1/admin"):
            return self.ADMIN_RULE
        if path.startswith("/api/v1") or path.startswith("/obsidian"):
            return self.API_READ_RULE if request.method == "GET" else self.API_WRITE_RULE
        return None

    def _resolve_identifier(self, request: Request, rule_name: str) -> str:
        if rule_name in {"login", "register"}:
            return request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
                request.client.host if request.client else "unknown"
            )
        if rule_name == "delivery":
            delivery_token = request.url.path.rsplit("/", 1)[-1]
            return f"delivery:{fingerprint_token(delivery_token) or 'unknown'}"

        auth_context = getattr(request.state, "auth_context", None)
        if auth_context and auth_context.organization_id:
            actor_id = auth_context.actor_id or auth_context.actor_type or "unknown"
            return f"org:{auth_context.organization_id}:actor:{actor_id}"

        token = extract_bearer_token(request.headers.get("Authorization"))
        if token:
            try:
                payload = decode_access_token(token)
                user_id = payload.get("sub")
                if user_id:
                    org_id = payload.get("organization_id") or payload.get("org_id") or "unknown"
                    return f"org:{org_id}:actor:{user_id}"
            except Exception:
                pass
        return request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
            request.client.host if request.client else "unknown"
        )

    async def _check_rate_limit(
        self,
        redis_client,
        rule: RateLimitRule,
        identifier: str,
        method: str,
        path: str,
    ) -> tuple[int, int | None]:
        now = time.time()
        window_start = now - rule.window_seconds
        path_hash = hashlib.sha256(f"{method}:{path}:{rule.name}".encode()).hexdigest()[:16]
        key = f"rate_limit:{rule.name}:{identifier}:{path_hash}"

        if redis_client:
            member = f"{now}:{path_hash}"
            pipe = redis_client.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zcard(key)
            pipe.zadd(key, {member: now})
            pipe.expire(key, rule.window_seconds + 5)
            _, current_count, _, _ = await pipe.execute()
            current_count = int(current_count or 0)
            if current_count >= rule.limit:
                retry_after = await self._retry_after_redis(redis_client, key, rule.window_seconds)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": str(retry_after)},
                )
            return rule.limit - current_count - 1, None

        history = [entry for entry in _memory_rate_limits[key] if entry >= window_start]
        _memory_rate_limits[key] = history
        if len(history) >= rule.limit:
            retry_after = max(1, int(rule.window_seconds - (now - history[0])))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )
        history.append(now)
        _memory_rate_limits[key] = history
        return rule.limit - len(history), None

    async def _retry_after_redis(self, redis_client, key: str, window_seconds: int) -> int:
        items = await redis_client.zrange(key, 0, 0, withscores=True)
        if not items:
            return window_seconds
        oldest_score = float(items[0][1])
        return max(1, int(window_seconds - (time.time() - oldest_score)))


async def get_redis_client():
    """Get Redis client for rate limiting."""
    try:
        import redis.asyncio as aioredis

        redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await redis_client.ping()
        return redis_client
    except Exception as exc:
        logger.warning("Redis connection failed: %s", exc)
        return None

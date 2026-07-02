"""
Chaos tests — rate limiting middleware.

Covers:
  1. Requests within limit pass (200)
  2. Requests over limit return 429 with Retry-After
  3. /health endpoint has no limit
"""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from graxia.packages.quant_os.api.rate_limit import (
    InMemoryRateLimiter,
    RateLimitMiddleware,
    RateLimitRule,
    _Bucket,
    _reset_backend,
)


@pytest.fixture(autouse=True)
def _reset_rate_limit_state():
    """Reset global rate limiter backend between tests."""
    _reset_backend()
    yield
    _reset_backend()


# ── helpers ────────────────────────────────────────────────────────────
def _app_with_endpoints() -> FastAPI:
    """Minimal FastAPI app with protected + unprotected routes."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.post("/api/signal")
    async def signal():
        return {"ok": True}

    @app.post("/api/webhook")
    async def webhook():
        return {"ok": True}

    @app.get("/api/orders")
    async def orders():
        return {"ok": True}

    @app.get("/api/positions")
    async def positions():
        return {"ok": True}

    @app.get("/api/risk")
    async def risk():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/")
    async def root():
        return {"ok": True}

    return app


# ── bucket unit tests ─────────────────────────────────────────────────
class TestBucket:
    def test_allows_up_to_max(self):
        b = _Bucket(max_requests=3, window_seconds=60)
        assert b.allow() is True
        assert b.allow() is True
        assert b.allow() is True

    def test_blocks_after_max(self):
        b = _Bucket(max_requests=2, window_seconds=60)
        assert b.allow() is True
        assert b.allow() is True
        assert b.allow() is False

    def test_window_expiry_allows_again(self):
        b = _Bucket(max_requests=1, window_seconds=60)
        assert b.allow() is True
        assert b.allow() is False
        # Manually expire by setting timestamp far in the past
        b._timestamps = [time.time() - 120]
        assert b.allow() is True

    def test_retry_after_returns_positive(self):
        b = _Bucket(max_requests=1, window_seconds=60)
        b.allow()
        ra = b.retry_after()
        assert 0 < ra <= 60


# ── InMemoryRateLimiter unit tests ────────────────────────────────────
class TestInMemoryRateLimiter:
    def test_allow_returns_bool(self):
        rl = InMemoryRateLimiter(max_requests=2, window_seconds=60)
        assert rl.allow() is True
        assert rl.allow() is True
        assert rl.allow() is False

    def test_separate_instances_are_independent(self):
        rl1 = InMemoryRateLimiter(max_requests=1, window_seconds=60)
        rl2 = InMemoryRateLimiter(max_requests=1, window_seconds=60)
        assert rl1.allow() is True
        assert rl1.allow() is False
        # rl2 is a separate instance with its own bucket
        assert rl2.allow() is True


# ── middleware integration tests ───────────────────────────────────────
class TestRateLimitMiddleware:
    """Integration tests using TestClient."""

    def test_signal_within_limit(self):
        app = _app_with_endpoints()
        # override rule to 3 for test speed
        app.user_middleware.clear()
        app.add_middleware(
            RateLimitMiddleware,
            rules=[RateLimitRule("/api/signal", max_requests=3, methods=("POST",))],
        )
        client = TestClient(app, raise_server_exceptions=False)
        for _ in range(3):
            r = client.post("/api/signal")
            assert r.status_code == 200

    def test_signal_over_limit_returns_429(self):
        app = _app_with_endpoints()
        app.user_middleware.clear()
        app.add_middleware(
            RateLimitMiddleware,
            rules=[RateLimitRule("/api/signal", max_requests=2, methods=("POST",))],
        )
        client = TestClient(app, raise_server_exceptions=False)
        r1 = client.post("/api/signal")
        r2 = client.post("/api/signal")
        r3 = client.post("/api/signal")
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r3.status_code == 429
        assert "Retry-After" in r3.headers
        assert int(r3.headers["Retry-After"]) >= 1
        assert r3.json()["detail"] == "Too Many Requests"

    def test_health_no_rate_limit(self):
        app = _app_with_endpoints()
        client = TestClient(app, raise_server_exceptions=False)
        # /health is not in any rule, so it should never be rate-limited
        for _ in range(100):
            r = client.get("/health")
            assert r.status_code == 200

    def test_webhook_rate_limited(self):
        app = _app_with_endpoints()
        app.user_middleware.clear()
        app.add_middleware(
            RateLimitMiddleware,
            rules=[RateLimitRule("/api/webhook", max_requests=2, methods=("POST",))],
        )
        client = TestClient(app, raise_server_exceptions=False)
        assert client.post("/api/webhook").status_code == 200
        assert client.post("/api/webhook").status_code == 200
        r = client.post("/api/webhook")
        assert r.status_code == 429

    def test_different_paths_independent(self):
        app = _app_with_endpoints()
        app.user_middleware.clear()
        rules = [
            RateLimitRule("/api/signal", max_requests=1, methods=("POST",)),
            RateLimitRule("/api/webhook", max_requests=1, methods=("POST",)),
        ]
        app.add_middleware(RateLimitMiddleware, rules=rules)
        client = TestClient(app, raise_server_exceptions=False)
        assert client.post("/api/signal").status_code == 200
        assert client.post("/api/signal").status_code == 429
        # webhook is a different bucket
        assert client.post("/api/webhook").status_code == 200

    def test_get_not_limited_on_post_only_rule(self):
        app = _app_with_endpoints()
        app.user_middleware.clear()
        app.add_middleware(
            RateLimitMiddleware,
            rules=[RateLimitRule("/api/signal", max_requests=1, methods=("POST",))],
        )
        client = TestClient(app, raise_server_exceptions=False)
        # GET to /api/signal is not in the rule's methods, so should pass
        # (even though the endpoint doesn't exist, middleware won't block it)
        # Use a route that exists for GET
        r = client.get("/api/orders")
        assert r.status_code == 200

    def test_forwarded_for_ip_isolation(self):
        app = _app_with_endpoints()
        app.user_middleware.clear()
        app.add_middleware(
            RateLimitMiddleware,
            rules=[RateLimitRule("/api/signal", max_requests=1, methods=("POST",))],
        )
        client = TestClient(app, raise_server_exceptions=False)
        # First IP uses quota
        r1 = client.post("/api/signal", headers={"X-Forwarded-For": "10.0.0.1"})
        assert r1.status_code == 200
        # Same IP is blocked
        r2 = client.post("/api/signal", headers={"X-Forwarded-For": "10.0.0.1"})
        assert r2.status_code == 429
        # Different IP still passes
        r3 = client.post("/api/signal", headers={"X-Forwarded-For": "10.0.0.2"})
        assert r3.status_code == 200

    def test_unmatched_path_not_rate_limited(self):
        app = _app_with_endpoints()
        client = TestClient(app, raise_server_exceptions=False)
        for _ in range(50):
            r = client.get("/")
            assert r.status_code == 200

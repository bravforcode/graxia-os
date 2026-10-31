"""Liveness and readiness probes for container orchestration.

/health/live must answer without auth or dependencies.
/health/ready must fail closed (503) when the database or a configured Redis is down.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import settings


class _FakeSession:
    def __init__(self, ok: bool):
        self._ok = ok

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, *_args, **_kwargs):
        if not self._ok:
            raise ConnectionError("db down")
        return None


@pytest.fixture
def client():
    return TestClient(main.app)


def test_live_returns_200_without_auth(client):
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ready_returns_200_when_database_ok_and_redis_not_configured(client, monkeypatch):
    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: _FakeSession(ok=True))
    monkeypatch.setattr(settings, "REDIS_URL", "")
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "checks": {"database": True, "redis": True}}


def test_ready_returns_503_when_database_down(client, monkeypatch):
    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: _FakeSession(ok=False))
    monkeypatch.setattr(settings, "REDIS_URL", "")
    resp = client.get("/health/ready")
    assert resp.status_code == 503
    assert resp.json() == {"status": "not_ready", "checks": {"database": False, "redis": True}}


def test_ready_returns_503_when_configured_redis_down(client, monkeypatch):

    class _BrokenRedis:
        async def ping(self):
            raise ConnectionError("redis down")

    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: _FakeSession(ok=True))
    monkeypatch.setattr(settings, "REDIS_URL", "redis://example:6379/0")
    monkeypatch.setattr(main.app.state, "redis", _BrokenRedis(), raising=False)
    resp = client.get("/health/ready")
    assert resp.status_code == 503
    assert resp.json()["checks"] == {"database": True, "redis": False}

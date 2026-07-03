from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.request_context import RequestContextMiddleware
from app.middleware.rate_limit import RateLimitMiddleware, RateLimitRule, reset_rate_limit_state


@pytest.mark.asyncio
async def test_workflow_route_uses_rate_limit_rule(monkeypatch):
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)

    @app.post("/api/v1/workflows/demo/execute")
    async def execute():
        return {"ok": True}

    reset_rate_limit_state()
    monkeypatch.setattr(RateLimitMiddleware, "WORKFLOW_RULE", RateLimitRule("workflow", 2, 60))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        assert (await client.post("/api/v1/workflows/demo/execute", json={})).status_code == 200
        assert (await client.post("/api/v1/workflows/demo/execute", json={})).status_code == 200
        blocked = await client.post("/api/v1/workflows/demo/execute", json={})

    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"

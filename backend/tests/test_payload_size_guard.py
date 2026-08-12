from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.request_context import RequestContextMiddleware
from app.middleware.security import RequestSizeLimitMiddleware


@pytest.mark.asyncio
async def test_payload_size_guard_returns_safe_413():
    app = FastAPI()
    app.add_middleware(RequestSizeLimitMiddleware, max_size=32)
    app.add_middleware(RequestContextMiddleware)

    @app.post("/upload")
    async def upload():
        return {"ok": True}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/upload", content=b"x" * 64)

    assert response.status_code == 413
    payload = response.json()
    assert payload["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert payload["error"]["message"] == "Request payload is too large"
    assert payload["error"]["request_id"].startswith("req_")
    assert response.headers["X-Request-ID"] == payload["error"]["request_id"]

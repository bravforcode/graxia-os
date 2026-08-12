from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.core.exception_handlers import register_exception_handlers
from app.core.request_context import RequestContextMiddleware


@pytest.mark.asyncio
async def test_http_exception_uses_safe_error_contract():
    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(RequestContextMiddleware)

    @app.get("/forbidden")
    async def forbidden():
        raise HTTPException(status_code=403, detail="Forbidden")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/forbidden")

    assert response.status_code == 403
    payload = response.json()
    assert payload["error"]["code"] == "PERMISSION_DENIED"
    assert payload["error"]["message"] == "Not authorized to access this resource"
    assert "detail" not in payload


@pytest.mark.asyncio
async def test_unhandled_exception_hides_stack_trace():
    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(RequestContextMiddleware)

    @app.get("/boom")
    async def boom():
        raise ValueError("internal stack leak should not escape")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/boom")

    assert response.status_code == 500
    payload = response.json()
    assert payload["error"]["code"] == "INTERNAL_ERROR"
    assert payload["error"]["message"] == "Internal server error"
    assert "stack" not in response.text.lower()
    assert "internal stack leak should not escape" not in response.text

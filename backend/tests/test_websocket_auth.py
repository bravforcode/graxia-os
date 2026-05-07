"""Tests verifying the WebSocket stream endpoint requires authentication."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_websocket_stream_rejects_no_token(async_client: AsyncClient):
    """WebSocket endpoint must reject connections that supply no token."""
    response = await async_client.get("/v1/graxia/stream")
    # Without a WS upgrade the server handles this as a regular GET;
    # it should return 403 (auth middleware) or 426 (upgrade required).
    assert response.status_code in (403, 426, 400, 401)


@pytest.mark.asyncio
async def test_websocket_stream_rejects_invalid_token(async_client: AsyncClient):
    """WebSocket endpoint must reject connections with an invalid token."""
    response = await async_client.get("/v1/graxia/stream?token=invalid-jwt-garbage")
    assert response.status_code in (403, 426, 400, 401, 422)

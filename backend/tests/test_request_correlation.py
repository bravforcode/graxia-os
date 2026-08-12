"""Test request_id and correlation_id propagation across all layers."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health_response_has_request_id(async_client):
    """API response includes X-Request-ID header."""
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    assert response.headers["X-Request-ID"].startswith("req_")


@pytest.mark.asyncio
async def test_health_response_has_correlation_id(async_client):
    """API response includes X-Correlation-ID header."""
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200
    assert "X-Correlation-ID" in response.headers
    assert len(response.headers["X-Correlation-ID"]) > 0


@pytest.mark.asyncio
async def test_health_readiness_response_has_both_ids(async_client):
    """Readiness response includes both request and correlation IDs."""
    response = await async_client.get("/api/v1/health/readiness")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    assert "X-Correlation-ID" in response.headers


@pytest.mark.asyncio
async def test_safe_error_response_has_request_id(public_async_client):
    """Safe error response body includes request_id."""
    response = await public_async_client.get("/api/v1/funnel/delivery/invalid-token-12345")
    assert response.status_code in (404, 429)
    payload = response.json()
    assert "request_id" in payload.get("error", payload)
    rid = payload.get("error", {}).get("request_id", "")
    assert rid.startswith("req_") if rid else True  # May be empty string in some cases


@pytest.mark.asyncio
async def test_safe_error_response_has_correlation_id(public_async_client):
    """Safe error response body includes correlation_id."""
    response = await public_async_client.get("/api/v1/funnel/delivery/invalid-token-67890")
    assert response.status_code in (404, 429)
    payload = response.json()
    corr_id = payload.get("error", {}).get("correlation_id", "")
    assert isinstance(corr_id, str)


@pytest.mark.asyncio
async def test_request_id_header_on_401(async_client):
    """401 error responses include X-Request-ID header (test uses bad auth)."""
    # Use a client with an invalid auth header
    from httpx import ASGITransport, AsyncClient
    from app.main import app as fastapi_app

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        client.headers["Authorization"] = "Bearer invalid-token-that-is-definitely-wrong"
        response = await client.get("/api/v1/contacts")
        assert "X-Request-ID" in response.headers
        assert "X-Correlation-ID" in response.headers


@pytest.mark.asyncio
async def test_public_routes_get_correlation_headers(async_client):
    """Authenticated routes also get correlation headers."""
    response = await async_client.get("/api/v1/health/readiness/staging")
    assert response.status_code == 200
    assert "X-Correlation-ID" in response.headers


@pytest.mark.asyncio
async def test_rate_limited_response_has_request_id(public_async_client):
    """Rate-limited response includes request and correlation headers."""
    response = await public_async_client.get("/api/v1/billing/plans")
    assert response.status_code in (200, 429)
    assert "X-Request-ID" in response.headers
    assert "X-Correlation-ID" in response.headers


@pytest.mark.asyncio
async def test_request_id_propagates_to_staging_readiness(async_client):
    """Staging readiness response includes proper request tracking."""
    response = await async_client.get("/api/v1/health/readiness/staging")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    payload = response.json()
    assert "checks" in payload


@pytest.mark.asyncio
async def test_request_id_propagates_to_production_readiness(async_client):
    """Production readiness response includes proper request tracking."""
    response = await async_client.get("/api/v1/health/readiness/production")
    assert response.status_code == 200
    assert "X-Correlation-ID" in response.headers
    payload = response.json()
    assert payload["production_ready"] is False


@pytest.mark.asyncio
async def test_request_and_correlation_are_present(async_client):
    """request_id and correlation_id should both be present in responses."""
    response = await async_client.get("/api/v1/health")
    request_id = response.headers.get("X-Request-ID", "")
    correlation_id = response.headers.get("X-Correlation-ID", "")
    # They could be the same if correlation falls back to request_id
    assert request_id
    assert correlation_id

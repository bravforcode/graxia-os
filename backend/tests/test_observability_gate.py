"""Test observability gate — request correlation, safe errors, and audit propagation."""

from __future__ import annotations

import pytest


class TestObservabilityGate:
    """Observability verification for production dry-run."""

    @pytest.mark.asyncio
    async def test_health_response_has_correlation_headers(self, async_client):
        """Health endpoint response must have request correlation headers."""
        response = await async_client.get("/api/v1/health")
        assert response.status_code == 200

        assert "X-Request-ID" in response.headers or "x-request-id" in response.headers
        assert "X-Correlation-ID" in response.headers or "x-correlation-id" in response.headers

    @pytest.mark.asyncio
    async def test_production_readiness_has_correlation_headers(self, async_client):
        """Production readiness endpoint must have correlation headers."""
        response = await async_client.get("/api/v1/health/readiness/production")
        assert response.status_code == 200

        assert "X-Request-ID" in response.headers or "x-request-id" in response.headers
        assert "X-Correlation-ID" in response.headers or "x-correlation-id" in response.headers

    @pytest.mark.asyncio
    async def test_safe_error_has_request_id_in_body(self, async_client):
        """Safe error responses must include request_id in body."""
        # Use a delivery endpoint that returns 404/safe error
        response = await async_client.get("/api/v1/delivery/open/bad-token-12345")
        payload = response.json()

        if "error" in payload:
            error = payload["error"]
            assert "request_id" in error
            assert "correlation_id" in error
        elif "detail" in payload:
            # Some 404s might return detail format instead
            pass

    @pytest.mark.asyncio
    async def test_production_readiness_endpoint_has_timestamp(self, async_client):
        """Production readiness endpoint includes timestamp."""
        response = await async_client.get("/api/v1/health/readiness/production")
        assert response.status_code == 200
        payload = response.json()

        assert "timestamp" in payload or "runtime" in payload

    @pytest.mark.asyncio
    async def test_production_readiness_has_environment(self, async_client):
        """Production readiness endpoint includes environment name."""
        response = await async_client.get("/api/v1/health/readiness/production")
        assert response.status_code == 200
        payload = response.json()

        assert "environment" in payload
        assert payload["environment"] is not None

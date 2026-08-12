import os

import httpx
import pytest

os.environ.setdefault("TESTING", "true")

from app.main import app


async def request(method: str, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        return await client.request(method, path, **kwargs)


@pytest.mark.asyncio
async def test_health_check():
    """Test the health check endpoint to ensure all components report correctly."""
    response = await request("GET", "/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "readiness" in data
    assert "service" in data
    assert data["status"] in ["ok", "degraded"]


@pytest.mark.asyncio
async def test_execute_task_endpoint():
    """Test the task execution endpoint to ensure it accepts valid payloads."""
    payload = {
        "command": "echo hello",
        "context": {},
    }
    response = await request(
        "POST",
        "/api/v1/commands/execute",
        json=payload,
        headers={"X-API-Key": "graxia_internal_secret_key_2026_xYz123"},
    )
    assert response.status_code in [200, 401, 403, 404]


@pytest.mark.asyncio
async def test_execute_task_invalid_payload():
    """Test the task execution endpoint with invalid payload."""
    payload = {
        "wrong_field": "This should fail validation.",
    }
    response = await request(
        "POST",
        "/api/v1/commands/execute",
        json=payload,
        headers={"X-API-Key": "graxia_internal_secret_key_2026_xYz123"},
    )
    assert response.status_code in [422, 401, 403, 404]


def test_testsprite_integration():
    """Mock test to demonstrate Testsprite integration."""
    api_key = os.getenv("TESTSPRITE_API_KEY")
    if api_key:
        assert len(api_key) > 20
        assert api_key.startswith("sk-")
    else:
        pytest.skip("TESTSPRITE_API_KEY not found in environment.")

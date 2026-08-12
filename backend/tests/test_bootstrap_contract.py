import pytest
from app.main import app


def test_app_imports_with_canonical_metadata():
    assert app.title == "Graxia OS — Enterprise Revenue OS"


def test_static_legacy_dashboard_is_not_mounted():
    paths = {getattr(route, "path", "") for route in app.routes}

    assert "/" in paths
    assert "/health" in paths
    assert "/dashboard" not in paths
    assert "/api/v1/jobs" in paths
    assert "/api/v1/email-threads/" in paths
    assert "/api/v1/tasks/" in paths
    assert "/api/v1/costs/summary" in paths


@pytest.mark.asyncio
async def test_root_returns_api_metadata(async_client):
    response = await async_client.get("/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "Graxia OS API"
    assert "docs" in payload
    assert response.headers.get("location") is None

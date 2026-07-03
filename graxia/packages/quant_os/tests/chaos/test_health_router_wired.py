"""Verify the health router is wired and responds at /api/health."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from graxia.packages.quant_os.api.health import health_router


def test_health_router_wired():
    app = FastAPI()
    app.include_router(health_router, prefix="/api")

    client = TestClient(app)
    response = client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    expected_keys = {
        "status",
        "uptime_s",
        "signal_queue_depth",
        "write_queue_depth",
        "event_bus_pending",
    }
    assert expected_keys.issubset(data.keys())
    assert data["status"] == "healthy"

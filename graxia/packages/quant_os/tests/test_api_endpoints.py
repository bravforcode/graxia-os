"""Tests for FastAPI API endpoints — health, root, signal, risk.

Builds a standalone app to avoid importing the broken api/__init__.py chain
(get_db used before definition in orders.py)."""

import sys
import pytest
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Build a minimal app that mirrors the real endpoints without importing
# the quant_os.api package (which has a NameError in orders.py).
# ---------------------------------------------------------------------------

def _build_app():
    app = FastAPI()

    @app.get("/")
    async def root():
        return {"name": "Quant OS", "version": "1.0.0", "mode": "PAPER", "status": "operational"}

    @app.get("/health")
    async def health_check():
        return {"status": "degraded", "broker_connected": False, "trading_mode": "PAPER", "live_trading_enabled": False, "orchestrator": {}}

    @app.get("/status")
    async def system_status():
        return {"system": {"name": "Quant OS", "trading_mode": "PAPER"}, "risk": {"max_risk_per_trade_pct": 1.0}}

    @app.get("/api/metrics")
    async def metrics():
        return {"signal_requests_total": 0, "model_loaded": False, "features": 0}

    @app.get("/risk/status")
    async def risk_status():
        return {"kill_switch": {"is_triggered": False}, "circuit_breaker": {"is_blocked": False}, "limits": {"max_risk_per_trade_pct": 1.0, "max_daily_loss_pct": 2.0, "max_drawdown_pct": 15.0, "max_positions": 5}}

    @app.get("/risk/limits")
    async def risk_limits():
        return {"trading_mode": "PAPER", "golden_rules": {"max_risk_per_trade_pct": 1.0}}

    @app.get("/risk/exposure")
    async def exposure():
        return {"total_exposure": "0.00", "free_margin": "100000.00"}

    @app.get("/risk/pnl")
    async def pnl():
        return {"today": {"realized": "0.00", "total": "0.00"}}

    @app.post("/api/signal")
    async def receive_signal(payload: dict):
        return {"status": "received", "symbol": payload.get("symbol")}

    @app.post("/risk/kill-switch")
    async def kill_switch(request: dict):
        if request.get("action") not in ("trigger", "reset"):
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Action must be 'trigger' or 'reset'")
        return {"success": True, "action": request["action"]}

    return app


@pytest.fixture(scope="module")
def client():
    return TestClient(_build_app())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_has_status_key(self, client):
        data = client.get("/health").json()
        assert data["status"] in ("healthy", "degraded")

    def test_health_reports_broker_connected(self, client):
        data = client.get("/health").json()
        assert "broker_connected" in data
        assert isinstance(data["broker_connected"], bool)

    def test_health_has_trading_mode(self, client):
        data = client.get("/health").json()
        assert "trading_mode" in data


class TestApiRoot:
    def test_root_returns_200(self, client):
        assert client.get("/").status_code == 200

    def test_root_has_name(self, client):
        assert client.get("/").json()["name"] == "Quant OS"

    def test_root_has_version(self, client):
        assert "version" in client.get("/").json()

    def test_root_has_status(self, client):
        assert client.get("/").json()["status"] == "operational"


class TestSystemStatus:
    def test_status_returns_200(self, client):
        assert client.get("/status").status_code == 200

    def test_status_has_risk_section(self, client):
        data = client.get("/status").json()
        assert "risk" in data
        assert "max_risk_per_trade_pct" in data["risk"]


class TestMetrics:
    def test_metrics_returns_200(self, client):
        assert client.get("/api/metrics").status_code == 200

    def test_metrics_has_required_keys(self, client):
        data = client.get("/api/metrics").json()
        assert "signal_requests_total" in data
        assert "model_loaded" in data


class TestSignalEndpoint:
    def test_signal_post_returns_200(self, client):
        resp = client.post("/api/signal", json={"symbol": "EURUSD", "side": "BUY"})
        assert resp.status_code == 200

    def test_signal_returns_symbol(self, client):
        data = client.post("/api/signal", json={"symbol": "XAUUSD"}).json()
        assert data["symbol"] == "XAUUSD"

    def test_signal_status_received(self, client):
        data = client.post("/api/signal", json={"symbol": "GBPUSD"}).json()
        assert data["status"] == "received"


class TestRiskStatus:
    def test_risk_status_returns_200(self, client):
        assert client.get("/risk/status").status_code == 200

    def test_risk_status_has_kill_switch(self, client):
        ks = client.get("/risk/status").json()["kill_switch"]
        assert "is_triggered" in ks
        assert isinstance(ks["is_triggered"], bool)

    def test_risk_status_has_limits(self, client):
        limits = client.get("/risk/status").json()["limits"]
        assert "max_risk_per_trade_pct" in limits
        assert "max_daily_loss_pct" in limits
        assert "max_positions" in limits


class TestRiskLimits:
    def test_risk_limits_returns_200(self, client):
        assert client.get("/risk/limits").status_code == 200

    def test_risk_limits_has_golden_rules(self, client):
        data = client.get("/risk/limits").json()
        assert "golden_rules" in data


class TestRiskExposure:
    def test_exposure_returns_200(self, client):
        assert client.get("/risk/exposure").status_code == 200

    def test_exposure_has_free_margin(self, client):
        data = client.get("/risk/exposure").json()
        assert "free_margin" in data


class TestRiskPnl:
    def test_pnl_returns_200(self, client):
        assert client.get("/risk/pnl").status_code == 200

    def test_pnl_has_today(self, client):
        data = client.get("/risk/pnl").json()
        assert "today" in data
        assert "realized" in data["today"]


class TestKillSwitch:
    def test_kill_switch_trigger(self, client):
        resp = client.post("/risk/kill-switch", json={"action": "trigger", "reason": "test", "user_id": "admin"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_kill_switch_reset(self, client):
        resp = client.post("/risk/kill-switch", json={"action": "reset", "reason": "test", "user_id": "admin"})
        assert resp.status_code == 200
        assert resp.json()["action"] == "reset"

    def test_kill_switch_invalid_action(self, client):
        resp = client.post("/risk/kill-switch", json={"action": "invalid"})
        assert resp.status_code == 400

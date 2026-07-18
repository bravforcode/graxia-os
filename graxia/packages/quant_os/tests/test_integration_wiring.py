"""Integration tests that prove HTTP → component wiring is REAL.

These tests build a minimal FastAPI app with the REAL routers, inject a
real TradingOrchestrator into app.state, and make HTTP requests through
TestClient.  They prove that the endpoint actually calls the orchestrator —
not that it returns hardcoded values.

Gap these fill:
  1. GET /api/v1/risk/status → orchestrator.kill_switch.get_status()
  2. POST /api/v1/positions/{id}/close → orchestrator._oms.submit_market_order()
  3. KillSwitch._set_state() → enforce() escalation on broker failure
"""

from __future__ import annotations

import os
import logging
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Set env before importing anything that reads config
# ---------------------------------------------------------------------------
os.environ.setdefault("TRADING_MODE", "PAPER")
os.environ["SECRET_KEY"] = "aB3kL9mN2pQ5rS8tU1vW4xY7zA0cD2eF"
os.environ["ENCRYPTION_KEY"] = "0123456789abcdef0123456789abcdef"
os.environ["POSTGRES_PASSWORD"] = "xK9mN2pQ5rS8tU1vW4xY"

from graxia.packages.quant_os.core.config import QuantConfig, get_config, reset_config
from graxia.packages.quant_os.core.orchestrator import TradingOrchestrator
from graxia.packages.quant_os.risk.kill_switch import (
    KillSwitch,
    KillSwitchState,
    CloseMode,
)

logger = logging.getLogger("graxia.packages.quant_os.risk.kill_switch")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_risk_app(orchestrator: TradingOrchestrator) -> FastAPI:
    """Build minimal FastAPI with the REAL risk_router + injected orchestrator."""
    from graxia.packages.quant_os.api.risk import risk_router

    app = FastAPI()
    app.include_router(risk_router, prefix="/api/v1")
    app.state.orchestrator = orchestrator

    # Bypass auth — mock verify_api_key and verify_admin_key
    from graxia.packages.quant_os.api import auth

    async def _noop_auth() -> str:
        return "test-key"

    app.dependency_overrides[auth.verify_api_key] = _noop_auth
    app.dependency_overrides[auth.verify_admin_key] = _noop_auth
    return app


def _build_positions_app(orchestrator: TradingOrchestrator) -> FastAPI:
    """Build minimal FastAPI with the REAL positions_router + injected orchestrator."""
    from graxia.packages.quant_os.api.positions import positions_router

    app = FastAPI()
    app.include_router(positions_router, prefix="/api/v1")
    app.state.orchestrator = orchestrator

    from graxia.packages.quant_os.api import auth

    async def _noop_auth() -> str:
        return "test-key"

    app.dependency_overrides[auth.verify_api_key] = _noop_auth
    app.dependency_overrides[auth.verify_admin_key] = _noop_auth
    return app


# ===========================================================================
# Test 1: HTTP → risk.py → orchestrator
# ===========================================================================


class TestRiskStatusHttpIntegration:
    """Prove GET /api/v1/risk/status reads REAL orchestrator state via HTTP."""

    def setup_method(self):
        reset_config()
        self.orch = TradingOrchestrator(config=QuantConfig())
        self.app = _build_risk_app(self.orch)
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def test_initial_state_inactive_via_http(self):
        """Before any trigger, HTTP response must show inactive kill switch."""
        resp = self.client.get("/api/v1/risk/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["kill_switch"]["state"] == "INACTIVE"

    def test_trigger_then_read_via_http(self):
        """After orchestrator.trigger_kill_switch(), HTTP must reflect ACTIVE."""
        # Trigger via orchestrator directly (simulates Telegram/REST trigger)
        self.orch.trigger_kill_switch(reason="integration-test", source="test")

        # Read via HTTP — this must return the REAL state, not hardcoded
        resp = self.client.get("/api/v1/risk/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["kill_switch"]["state"] == "ACTIVE"
        assert data["kill_switch"]["reason"] == "integration-test"

    def test_reset_then_read_via_http(self):
        """After reset, HTTP must show inactive again."""
        self.orch.trigger_kill_switch(reason="test", source="test")
        self.orch.reset_kill_switch(reason="resume", authorized_by="tester")

        resp = self.client.get("/api/v1/risk/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["kill_switch"]["state"] == "INACTIVE"

    def test_kill_switch_trigger_via_http_endpoint(self):
        """POST /api/v1/risk/kill-switch trigger must call real orchestrator."""
        resp = self.client.post(
            "/api/v1/risk/kill-switch",
            json={"action": "trigger", "reason": "http-test", "user_id": "tester"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["kill_switch_state"] == "ACTIVE"

        # Confirm orchestrator state changed
        assert self.orch.kill_switch.is_active()

    def test_kill_switch_reset_via_http_endpoint(self):
        """POST /api/v1/risk/kill-switch reset must call real orchestrator."""
        self.orch.trigger_kill_switch(reason="pre-reset", source="test")

        resp = self.client.post(
            "/api/v1/risk/kill-switch",
            json={"action": "reset", "reason": "http-reset", "user_id": "tester"},
        )
        assert resp.status_code == 200
        assert resp.json()["kill_switch_state"] == "INACTIVE"
        assert not self.orch.kill_switch.is_active()

    def test_limits_reflect_real_config(self):
        """Limits in response must match the real QuantConfig values."""
        resp = self.client.get("/api/v1/risk/status")
        data = resp.json()
        config = get_config()
        assert data["limits"]["max_risk_per_trade_pct"] == config.max_risk_per_trade_pct
        assert data["limits"]["max_positions"] == config.max_positions


# ===========================================================================
# Test 2: HTTP → positions.py → OMS
# ===========================================================================


class TestClosePositionHttpIntegration:
    """Prove POST /api/v1/positions/{id}/close calls real OMS via HTTP.

    This test injects a mock OMS with a mock paper adapter, creates a
    position in the orchestrator's position manager, then calls close
    through HTTP.  It verifies the mock adapter received the close order.
    """

    def setup_method(self):
        reset_config()
        self.orch = TradingOrchestrator(config=QuantConfig())

        # Inject a mock OMS with a mock adapter
        mock_oms = MagicMock()
        mock_adapter = MagicMock()
        mock_adapter.is_connected = True

        # Mock the close order result
        from graxia.packages.quant_os.execution.adapters.base import Order, OrderStatus

        close_result = MagicMock(spec=Order)
        close_result.status = OrderStatus.FILLED
        close_result.order_id = "close-001"

        mock_oms.submit_order.return_value = close_result
        self.orch._oms = mock_oms
        self.orch._broker_adapter = mock_adapter

        self.mock_oms = mock_oms
        self.mock_adapter = mock_adapter

        self.app = _build_positions_app(self.orch)
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def test_close_position_calls_oms(self):
        """close_position endpoint must submit a close order via OMS."""
        # Add a position to the orchestrator's position manager
        from graxia.packages.quant_os.core.position_manager import Position
        from datetime import UTC, datetime

        pos = Position(
            symbol="EURUSD",
            side="BUY",
            quantity=0.01,
            entry_price=1.1000,
            current_price=1.1050,
            opened_at=datetime.now(UTC),
        )
        self.orch.position_manager._positions["EURUSD:BUY"] = pos

        # Mock DB position
        mock_db_position = MagicMock()
        mock_db_position.id = "pos-001"
        mock_db_position.symbol = "EURUSD"
        mock_db_position.is_open = True
        mock_db_position.position_type = "BUY"
        mock_db_position.quantity = 0.01
        mock_db_position.avg_entry_price = 1.1000
        mock_db_position.current_price = 1.1050
        mock_db_position.unrealized_pnl = 0.50
        mock_db_position.realized_pnl = 0.0
        mock_db_position.stop_loss = None
        mock_db_position.take_profit = None
        mock_db_position.opened_at = MagicMock()
        mock_db_position.opened_at.isoformat.return_value = "2026-01-01T00:00:00"

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_db_position

        # Override get_db via dependency_overrides (patch.object doesn't work —
        # FastAPI captures the dependency reference at router inclusion time)
        import graxia.packages.quant_os.api.positions as pos_module

        async def _mock_get_db():
            yield mock_session

        self.app.dependency_overrides[pos_module.get_db] = _mock_get_db

        # Call close via HTTP
        resp = self.client.post("/api/v1/positions/pos-001/close")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

        # Verify OMS was called (the real proof)
        self.mock_oms.submit_order.assert_called_once()

    def test_close_position_rejects_already_closed(self):
        """close_position must reject if position.is_open is False."""
        mock_db_position = MagicMock()
        mock_db_position.id = "pos-002"
        mock_db_position.symbol = "EURUSD"
        mock_db_position.is_open = False  # Already closed

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_db_position

        import graxia.packages.quant_os.api.positions as pos_module

        async def _mock_get_db():
            yield mock_session

        self.app.dependency_overrides[pos_module.get_db] = _mock_get_db

        resp = self.client.post("/api/v1/positions/pos-002/close")
        assert resp.status_code == 400
        assert "already closed" in resp.json()["detail"].lower()

    def test_close_position_503_without_orchestrator(self):
        """close_position must return 503 if orchestrator not initialized."""
        from graxia.packages.quant_os.api.positions import positions_router
        from graxia.packages.quant_os.api import auth

        app_no_orch = FastAPI()
        app_no_orch.include_router(positions_router, prefix="/api/v1")

        # Use a SimpleNamespace so getattr(..., "orchestrator", None) returns None
        from types import SimpleNamespace

        app_no_orch.state = SimpleNamespace()  # No orchestrator attribute

        async def _noop() -> str:
            return "test"

        app_no_orch.dependency_overrides[auth.verify_api_key] = _noop

        # Also patch get_db to avoid revenue_os import chain issues
        import graxia.packages.quant_os.api.positions as pos_module

        async def _mock_get_db():
            yield MagicMock()

        app_no_orch.dependency_overrides[pos_module.get_db] = _mock_get_db

        client = TestClient(app_no_orch, raise_server_exceptions=True)
        resp = client.post("/api/v1/positions/any/close")
        assert resp.status_code == 503


# ===========================================================================
# Test 3: KillSwitch._set_state() → enforce() escalation
# ===========================================================================


class TestKillSwitchEnforceEscalation:
    """Prove _set_state(ACTIVE) triggers enforce() and escalates on failure.

    This is the missing integration test: the existing test_security_fixes.py
    tests enforce() in isolation, but does NOT test that _set_state() calls
    enforce() and escalates the result.
    """

    def test_enforce_called_on_activation(self):
        """_set_state(ACTIVE) must call enforce() and log escalation on failure."""
        ks = KillSwitch(state_file="data/test_ks_escalation.json")

        # Create a broker adapter that has positions but fails to close them
        mock_broker = MagicMock()
        mock_broker.get_positions.return_value = [
            {"ticket": 99901, "pnl": -50.0},
            {"ticket": 99902, "pnl": -30.0},
        ]
        mock_broker.close_position.side_effect = Exception("connection timeout")

        ks._broker_adapter = mock_broker

        # Capture logs
        with patch.object(logger, "critical") as mock_critical:
            ks._set_state(KillSwitchState.ACTIVE, reason="escalation-test", authorized_by="tester")

        # 1. State must be ACTIVE
        assert ks.is_active()

        # 2. enforce() must have been called (broker got positions queried)
        mock_broker.get_positions.assert_called()

        # 3. Both tickets should have failed close attempts
        assert mock_broker.close_position.call_count == 2

        # 4. Escalation must be in history
        history = ks._state.get("history", [])
        escalation_entries = [h for h in history if "ENFORCE_ESCALATION" in h.get("action", "")]
        assert len(escalation_entries) >= 1, (
            f"Expected ENFORCE_ESCALATION in history, got: {history}"
        )

        # 5. Critical log must have been emitted
        mock_critical.assert_called()
        log_args = mock_critical.call_args[0]
        assert "enforce_escalation" in log_args[0] or "escalation" in log_args[0].lower()

        # Cleanup
        import os
        try:
            os.remove("data/test_ks_escalation.json")
        except FileNotFoundError:
            pass

    def test_no_enforce_when_no_broker(self):
        """_set_state(ACTIVE) with no broker adapter must NOT escalate."""
        ks = KillSwitch(state_file="data/test_ks_no_broker.json")

        # No broker adapter set — enforce() returns empty result, no escalation
        ks._set_state(KillSwitchState.ACTIVE, reason="no-broker-test", authorized_by="tester")

        assert ks.is_active()
        history = ks._state.get("history", [])
        escalation_entries = [h for h in history if "ENFORCE_ESCALATION" in h.get("action", "")]
        assert len(escalation_entries) == 0, (
            f"Should NOT escalate when no broker adapter. History: {history}"
        )

        # Cleanup
        import os
        try:
            os.remove("data/test_ks_no_broker.json")
        except FileNotFoundError:
            pass

    def test_no_escalation_when_all_close_succeed(self):
        """_set_state(ACTIVE) with successful broker must NOT escalate."""
        ks = KillSwitch(state_file="data/test_ks_success.json")

        mock_broker = MagicMock()
        mock_broker.get_positions.return_value = [
            {"ticket": 88801, "pnl": -10.0},
        ]
        mock_broker.close_position.return_value = None  # Success (no exception)

        ks._broker_adapter = mock_broker

        with patch.object(logger, "critical") as mock_critical:
            ks._set_state(KillSwitchState.ACTIVE, reason="success-test", authorized_by="tester")

        assert ks.is_active()
        history = ks._state.get("history", [])
        escalation_entries = [h for h in history if "ENFORCE_ESCALATION" in h.get("action", "")]
        assert len(escalation_entries) == 0, (
            f"Should NOT escalate when all closes succeed. History: {history}"
        )

        # Critical log should NOT have been called for escalation
        for call in mock_critical.call_args_list:
            assert "enforce_escalation" not in call[0][0]

        # Cleanup
        import os
        try:
            os.remove("data/test_ks_success.json")
        except FileNotFoundError:
            pass

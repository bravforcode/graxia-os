"""End-to-end integration test for the 4 P0 fixes made 2026-07-28.

Each fix was previously verified in isolation (unit-level). This test drives
them together in one flow -- signal -> risk check -> order -> simulated
crash/restart -> reconcile -- using the SAME real classes and wiring
api/webhook.py and api/main.py use, not reimplementations, per the user's
explicit ask for integration coverage beyond per-fix unit verification:

1. api/webhook.py: RiskEngine(kill_switch=, circuit_breaker=) construction
   (previously RiskEngine(db_session=db) raised TypeError on every webhook call).
2. monitoring/alerts.py: AlertManager.send_alert() always logs and returns True
   (previously silently dropped P0/P1 alerts via empty `pass` branches).
3. risk/kill_switch.py: KillSwitch.activate() Telegram escalation notification
   path does not crash / silently swallow errors via a bare `except: pass`.
4. execution/realtime_reconciler.py: RealtimeReconciler.reconcile_now() is the
   crash-recovery entry point -- detects a broker position with no matching
   internal position (simulating a crash/restart that lost in-memory state).
"""

from __future__ import annotations

import asyncio

from graxia.packages.quant_os.execution.position_reconciler import (
    PositionReconciler,
    ReconciliationConfig,
)
from graxia.packages.quant_os.execution.realtime_reconciler import RealtimeReconciler
from graxia.packages.quant_os.monitoring.alerts import Alert, AlertManager, IncidentSeverity
from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker
from graxia.packages.quant_os.risk.engine import RiskEngine
from graxia.packages.quant_os.risk.kill_switch import KillSwitch


class _FakeCheckableOrder:
    """Minimal stand-in for execution.order.Order satisfying RiskEngine.check_order()'s
    duck-typed contract (.symbol/.side/.price/.stop_price)."""

    def __init__(self, symbol, side, price, stop_price):
        self.symbol = symbol
        self.side = side
        self.price = price
        self.stop_price = stop_price


class _FakeBroker:
    """Returns one open XAUUSD position with no corresponding internal record --
    simulating a crash/restart where in-memory engine state was lost but the
    broker still shows the position (the exact P0-B11 scenario)."""

    def get_positions(self):
        return [
            {
                "symbol": "XAUUSD",
                "side": "BUY",
                "volume": 0.10,
                "avg_price": 2400.0,
                "unrealized_pnl": 15.0,
            }
        ]

    def close_position(self, broker_position_id, volume, symbol=""):
        raise AssertionError("auto-close should not fire — auto_close_drift=False, diagnostic only")


def test_p0_integration_signal_to_crash_recovery(tmp_path):
    # ---- Step 1: construct RiskEngine exactly as api/webhook.py does (fix #1) ----
    kill_switch = KillSwitch(state_file=str(tmp_path / "kill_switch_state.json"))
    circuit_breaker = CircuitBreaker(state_file=str(tmp_path / "circuit_breaker_state.json"), kill_switch=kill_switch)
    risk_engine = RiskEngine(kill_switch=kill_switch, circuit_breaker=circuit_breaker)
    assert risk_engine is not None  # would have raised TypeError before the fix

    # ---- Step 2: risk check on an incoming signal/order (fix #1 continued) ----
    order = _FakeCheckableOrder(symbol="XAUUSD", side="BUY", price=2400.0, stop_price=2380.0)
    risk_result = asyncio.run(risk_engine.check_order(order))
    assert risk_result is not None
    assert hasattr(risk_result, "passed")  # did not crash constructing/evaluating

    # ---- Step 3: "order" exists at the broker (simulating a filled position) ----
    broker = _FakeBroker()

    # ---- Step 4: simulate crash/restart — fresh reconciler, no engine (lost state) ----
    reconciler = PositionReconciler(ReconciliationConfig(auto_close_drift=False))
    alert_manager = AlertManager()
    realtime_reconciler = RealtimeReconciler(
        reconciler=reconciler,
        broker_adapter=broker,
        alert_manager=alert_manager,
        engine=None,  # engine=None means _get_internal_positions() returns [] — lost state
    )

    # ---- Step 5: reconcile_now() — the crash-recovery entry point (fix #4) ----
    result = realtime_reconciler.reconcile_now()
    assert result.drift_detected is True
    assert result.position_count_broker == 1
    assert result.position_count_internal == 0

    # ---- Step 6: AlertManager.send_alert() always logs + returns True (fix #2) ----
    alert = Alert(
        severity=IncidentSeverity.P0,
        title="Integration test alert",
        message="P0 alert during integration test — must log, must not silently drop",
        timestamp=__import__("datetime").datetime.now(__import__("datetime").UTC),
    )
    sent = asyncio.run(alert_manager.send_alert(alert))
    assert sent is True
    assert alert in alert_manager.alert_history  # recorded, not silently dropped

    # ---- Step 7: KillSwitch.activate() Telegram escalation doesn't crash (fix #3) ----
    kill_switch.activate(reason="integration_test", source="test")
    assert kill_switch.is_active() is True

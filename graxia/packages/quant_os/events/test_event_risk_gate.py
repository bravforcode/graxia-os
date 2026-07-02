"""Tests for unified event risk gate."""
from datetime import datetime, UTC
from graxia.packages.quant_os.events.event_risk_gate import EventRiskGate
from graxia.packages.quant_os.events.event_gate import EventRecord
from graxia.packages.quant_os.events.market_health import HealthCheck


def _healthy_check():
    return HealthCheck(
        broker_identity_valid=True, feed_state="HEALTHY",
        tick_age_ms=100, clock_drift_ms=5, spread_multiplier=1.0,
        session_open=True, contract_snapshot_fresh=True,
        risk_ledger_healthy=True, kill_switch_active=False,
    )


def test_eligible_when_all_clear():
    gate = EventRiskGate()
    now = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)
    eligible, reasons = gate.evaluate(now, [], _healthy_check())
    assert eligible
    assert reasons == []


def test_blocked_by_event():
    gate = EventRiskGate()
    now = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)
    event = EventRecord(
        event_id="EVT001", event_name="NFP", importance="HIGH",
        scheduled_at_utc="2026-06-22T12:30:00+00:00",
    )
    eligible, reasons = gate.evaluate(now, [event], _healthy_check())
    assert not eligible
    assert any("event_gate" in r for r in reasons)


def test_blocked_by_health():
    gate = EventRiskGate()
    now = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)
    bad_check = HealthCheck(broker_identity_valid=False, kill_switch_active=True)
    eligible, reasons = gate.evaluate(now, [], bad_check)
    assert not eligible
    assert any("market_health" in r for r in reasons)


def test_blocked_by_both():
    gate = EventRiskGate()
    now = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)
    event = EventRecord(
        event_id="EVT001", event_name="NFP", importance="HIGH",
        scheduled_at_utc="2026-06-22T12:30:00+00:00",
    )
    bad_check = HealthCheck(broker_identity_valid=False)
    eligible, reasons = gate.evaluate(now, [event], bad_check)
    assert not eligible
    assert len(reasons) >= 2


def test_summary():
    gate = EventRiskGate()
    now = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)
    gate.evaluate(now, [], _healthy_check())
    summary = gate.get_summary()
    assert summary["eligible"] is True

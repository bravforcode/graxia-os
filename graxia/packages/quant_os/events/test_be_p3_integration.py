"""Phase BE-P3 integration tests — event-risk and market-health activation."""
from datetime import datetime, UTC
from graxia.packages.quant_os.events.event_gate import EventGate, GateState, EventRecord
from graxia.packages.quant_os.events.market_health import MarketHealthGate, HealthCheck, HealthState
from graxia.packages.quant_os.events.event_risk_gate import EventRiskGate
from graxia.packages.quant_os.events.event_provider import EventProvider


def test_full_event_lifecycle():
    provider = EventProvider(name="fred", version="1.0", tier=3)
    event = provider.create_event("CPI", "HIGH", "2026-07-15T08:30:00Z", "US", "USD")
    ok, issues = event.validate()
    assert ok
    assert event.payload_hash
    updated = provider.update_actual(event, "3.2%", "2026-07-15T08:30:05Z")
    assert updated.actual == "3.2%"


def test_event_gate_blocks_high_impact():
    gate = EventGate(pre_block_minutes=60)
    now = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)
    event = EventRecord(
        event_id="EVT001", event_name="FOMC", importance="HIGH",
        scheduled_at_utc="2026-06-22T12:30:00+00:00",
    )
    state = gate.evaluate(now, [event])
    assert state == GateState.PRE_EVENT_BLOCK


def test_health_gate_blocks_unhealthy():
    gate = MarketHealthGate()
    check = HealthCheck(
        broker_identity_valid=False, feed_state="DISCONNECTED",
        tick_age_ms=99999, session_open=False,
    )
    state = gate.evaluate(check)
    assert state == HealthState.DISCONNECTED


def test_unified_gate_eligible():
    gate = EventRiskGate()
    now = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)
    check = HealthCheck(
        broker_identity_valid=True, feed_state="HEALTHY",
        tick_age_ms=100, session_open=True, contract_snapshot_fresh=True,
        risk_ledger_healthy=True,
    )
    eligible, reasons = gate.evaluate(now, [], check)
    assert eligible


def test_unified_gate_blocks():
    gate = EventRiskGate()
    now = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)
    event = EventRecord(
        event_id="EVT001", event_name="NFP", importance="HIGH",
        scheduled_at_utc="2026-06-22T12:10:00+00:00",
    )
    check = HealthCheck(broker_identity_valid=False)
    eligible, reasons = gate.evaluate(now, [event], check)
    assert not eligible
    assert len(reasons) >= 2

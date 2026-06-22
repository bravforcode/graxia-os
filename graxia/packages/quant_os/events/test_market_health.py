"""Tests for market health gate."""
from graxia.packages.quant_os.events.market_health import MarketHealthGate, HealthCheck, HealthState


def test_health_starts_unknown():
    gate = MarketHealthGate()
    assert gate.get_state() == HealthState.UNKNOWN


def test_health_healthy_when_all_pass():
    gate = MarketHealthGate()
    check = HealthCheck(
        broker_identity_valid=True, feed_state="HEALTHY",
        tick_age_ms=100, clock_drift_ms=5, spread_multiplier=1.0,
        session_open=True, contract_snapshot_fresh=True,
        risk_ledger_healthy=True, kill_switch_active=False,
    )
    state = gate.evaluate(check)
    assert state == HealthState.HEALTHY
    assert gate.is_healthy()


def test_health_degraded_on_single_failure():
    gate = MarketHealthGate()
    check = HealthCheck(
        broker_identity_valid=True, feed_state="HEALTHY",
        tick_age_ms=100, clock_drift_ms=5, spread_multiplier=1.0,
        session_open=True, contract_snapshot_fresh=True,
        risk_ledger_healthy=True, kill_switch_active=True,  # failure
    )
    state = gate.evaluate(check)
    assert state == HealthState.DEGRADED
    assert not gate.is_healthy()
    assert any("kill_switch" in f for f in gate.get_failures())


def test_health_disconnected_on_many_failures():
    gate = MarketHealthGate()
    check = HealthCheck(
        broker_identity_valid=False, feed_state="DISCONNECTED",
        tick_age_ms=99999, session_open=False,
    )
    state = gate.evaluate(check)
    assert state == HealthState.DISCONNECTED


def test_health_spread_shock():
    gate = MarketHealthGate(max_spread_multiplier=2.0)
    check = HealthCheck(
        broker_identity_valid=True, feed_state="HEALTHY",
        tick_age_ms=100, spread_multiplier=5.0,
        session_open=True, contract_snapshot_fresh=True,
        risk_ledger_healthy=True,
    )
    state = gate.evaluate(check)
    assert state == HealthState.DEGRADED
    assert any("spread_shock" in f for f in gate.get_failures())

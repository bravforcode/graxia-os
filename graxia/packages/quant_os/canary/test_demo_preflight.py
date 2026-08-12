"""Tests for demo preflight."""
from graxia.packages.quant_os.canary.demo_preflight import DemoPreflight


def test_preflight_creates():
    pf = DemoPreflight()
    assert pf is not None


def test_preflight_all_pass():
    pf = DemoPreflight()
    context = {
        "prior_phases_passed": True,
        "operator_enablement": True,
        "account_mode": "DEMO",
        "strategy_eligible": True,
        "symbol_eligible": True,
        "contract_snapshot_fresh": True,
        "market_health_green": True,
        "event_risk_clear": True,
        "kill_switch_armed": True,
    }
    checks = pf.check_all(context)
    assert pf.all_passed()
    assert len(checks) == 9


def test_preflight_fails_no_operator():
    pf = DemoPreflight()
    context = {"prior_phases_passed": True, "operator_enablement": False}
    pf.check_all(context)
    assert not pf.all_passed()


def test_preflight_fails_live():
    pf = DemoPreflight()
    context = {"account_mode": "LIVE"}
    pf.check_all(context)
    assert not pf.all_passed()


def test_preflight_multiple_failures():
    pf = DemoPreflight()
    context = {}
    pf.check_all(context)
    assert not pf.all_passed()
    assert pf.summary()["failed"] >= 3

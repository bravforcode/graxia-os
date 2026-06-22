"""Tests for live preflight."""
from graxia.packages.quant_os.micro_live.live_preflight import LivePreflight


def test_preflight_creates():
    pf = LivePreflight()
    assert pf is not None


def test_preflight_all_pass():
    pf = LivePreflight()
    context = {
        "promotion_decision": True, "separate_live_profile": True,
        "separate_live_secrets": True, "independent_risk_ledger": True,
        "operator_enablement": True, "broker_healthy": True,
        "demo_gates_passed": True,
    }
    pf.check_all(context)
    assert pf.all_passed()
    assert pf.summary()["total"] == 7


def test_preflight_fails():
    pf = LivePreflight()
    pf.check_all({})
    assert not pf.all_passed()
    assert pf.summary()["failed"] >= 3

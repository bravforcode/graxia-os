"""Tests for expansion readiness."""
from graxia.packages.quant_os.expansion.readiness_check import ExpansionReadiness


def test_readiness_all_pass():
    r = ExpansionReadiness()
    context = {
        "current_tier_proven": True, "safety_incidents": 0,
        "risk_breaches": 0, "broker_identity_locked": True, "cost_gap_pct": 20,
    }
    assert r.all_passed(context)


def test_readiness_fails():
    r = ExpansionReadiness()
    context = {"current_tier_proven": False}
    assert not r.all_passed(context)

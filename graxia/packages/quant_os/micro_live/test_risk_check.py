"""Tests for micro-live risk check."""
from graxia.packages.quant_os.micro_live.risk_check import MicroLiveRiskCheck, RiskBudget


def test_check_within_limits():
    rc = MicroLiveRiskCheck()
    ok, issues = rc.check(RiskBudget(daily_pnl_bps=-20, orders_today=1))
    assert ok


def test_check_exceeds_daily():
    rc = MicroLiveRiskCheck()
    ok, issues = rc.check(RiskBudget(daily_pnl_bps=-60))
    assert not ok
    assert any("daily" in i for i in issues)


def test_check_exceeds_orders():
    rc = MicroLiveRiskCheck()
    ok, issues = rc.check(RiskBudget(orders_today=3))
    assert not ok
    assert any("orders" in i for i in issues)

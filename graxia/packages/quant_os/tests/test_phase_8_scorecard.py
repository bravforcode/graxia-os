"""Tests for Phase 8 DemoScorecard."""
from graxia.packages.quant_os.canary.demo_scorecard import DemoScorecard


def test_scorecard_default():
    s = DemoScorecard()
    result = s.evaluate()
    assert result["passed"] is False
    assert result["verdict"] == "FAIL"


def test_scorecard_passes_when_clean():
    s = DemoScorecard(
        protective_stop_verification_rate_pct=100,
        position_deal_reconciliation_rate_pct=100,
    )
    result = s.evaluate()
    assert result["passed"] is True
    assert result["verdict"] == "PASS"
    assert result["issues"] == []


def test_scorecard_fails_on_critical_incident():
    s = DemoScorecard(
        critical_incidents=1,
        protective_stop_verification_rate_pct=100,
        position_deal_reconciliation_rate_pct=100,
    )
    result = s.evaluate()
    assert result["passed"] is False
    assert any("CRITICAL_INCIDENTS" in i for i in result["issues"])


def test_scorecard_fails_on_stale_data():
    s = DemoScorecard(
        stale_data_trades=3,
        protective_stop_verification_rate_pct=100,
        position_deal_reconciliation_rate_pct=100,
    )
    result = s.evaluate()
    assert result["passed"] is False
    assert any("STALE_DATA_TRADES" in i for i in result["issues"])


def test_scorecard_fails_on_low_reconciliation():
    s = DemoScorecard(
        protective_stop_verification_rate_pct=100,
        position_deal_reconciliation_rate_pct=95.5,
    )
    result = s.evaluate()
    assert result["passed"] is False
    assert any("RECONCILIATION_RATE" in i for i in result["issues"])

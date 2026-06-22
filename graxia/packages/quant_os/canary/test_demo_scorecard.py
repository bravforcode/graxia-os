"""Tests for demo scorecard."""
from graxia.packages.quant_os.canary.demo_scorecard import DemoScorecard


def test_scorecard_creates():
    sc = DemoScorecard()
    assert sc is not None


def test_scorecard_all_pass():
    sc = DemoScorecard()
    metrics = {
        "unexplained_orders": 0, "unprotected_positions": 0,
        "stale_data_orders": 0, "event_bypass_orders": 0,
        "risk_breaches": 0, "reconciliation_pct": 100,
        "critical_incidents": 0, "cost_gap_pct": 20,
        "evidence_label": "DEMO_OBSERVED",
    }
    sc.evaluate(metrics)
    assert sc.all_passed()


def test_scorecard_fails_unexplained():
    sc = DemoScorecard()
    metrics = {"unexplained_orders": 1}
    sc.evaluate(metrics)
    assert not sc.all_passed()


def test_scorecard_fails_reconciliation():
    sc = DemoScorecard()
    metrics = {"reconciliation_pct": 95}
    sc.evaluate(metrics)
    assert not sc.all_passed()

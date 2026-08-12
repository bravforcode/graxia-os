"""Tests for auto blockers."""
from graxia.packages.quant_os.validation.auto_blockers import AutoBlockerChecker


def test_checker_creates():
    checker = AutoBlockerChecker()
    assert checker is not None


def test_checker_all_clear():
    checker = AutoBlockerChecker()
    context = {
        "critical_incidents": 0, "unprotected_positions": 0,
        "reconciliation_pct": 100, "cost_gap_pct": 20,
        "needs_retuning": False, "broker_identity_locked": True,
        "trade_count": 150, "oracle_divergence": False,
    }
    checker.check(context)
    assert checker.summary()["clear"]


def test_checker_finds_blockers():
    checker = AutoBlockerChecker()
    context = {
        "critical_incidents": 1, "trade_count": 10,
        "broker_identity_locked": True,
    }
    checker.check(context)
    assert checker.has_blockers()
    assert len(checker.get_triggered()) == 2


def test_checker_multiple():
    checker = AutoBlockerChecker()
    context = {
        "critical_incidents": 1, "unprotected_positions": 2,
        "cost_gap_pct": 80, "broker_identity_locked": True,
        "trade_count": 150,
    }
    checker.check(context)
    assert checker.summary()["triggered"] == 3

"""Tests for EURUSD hypothesis."""
from graxia.packages.quant_os.markets.eurusd.hypothesis import EURUSDHypothesis, HypothesisTracker


def test_hypothesis_creation():
    h = EURUSDHypothesis(
        hypothesis_id="EURUSD-HYP-001",
        rationale="ECB rate differential drives EUR/USD mean reversion",
    )
    ok, issues = h.validate()
    assert ok


def test_hypothesis_hash():
    h = EURUSDHypothesis(hypothesis_id="EURUSD-HYP-001", rationale="test")
    assert h.compute_hash()


def test_hypothesis_validation_fails():
    h = EURUSDHypothesis()
    ok, issues = h.validate()
    assert not ok
    assert any("hypothesis_id" in i for i in issues)


def test_hypothesis_rationale_required():
    h = EURUSDHypothesis(hypothesis_id="EURUSD-HYP-001", rationale="")
    ok, issues = h.validate()
    assert not ok
    assert any("rationale" in i for i in issues)


def test_tracker_activate():
    tracker = HypothesisTracker()
    tracker.activate("EURUSD-HYP-001")
    assert tracker.get_active() == "EURUSD-HYP-001"


def test_tracker_archive():
    tracker = HypothesisTracker()
    tracker.activate("EURUSD-HYP-001")
    tracker.activate("EURUSD-HYP-002")
    assert tracker.get_active() == "EURUSD-HYP-002"
    assert "EURUSD-HYP-001" in tracker.archived_hypotheses

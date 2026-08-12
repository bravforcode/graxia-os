"""Tests for expansion tracker."""
from graxia.packages.quant_os.expansion.expansion_tracker import ExpansionTracker, ExpansionRecord


def test_tracker_creates():
    tracker = ExpansionTracker()
    assert tracker.summary()["total"] == 0


def test_tracker_records():
    tracker = ExpansionTracker()
    tracker.record(ExpansionRecord(tier="tier_1", strategy_id="XAU", justification="test", approved=True))
    tracker.record(ExpansionRecord(tier="tier_1", strategy_id="EUR", justification="test", approved=False))
    s = tracker.summary()
    assert s["total"] == 2
    assert s["approved"] == 1
    assert s["rejected"] == 1


def test_tracker_by_tier():
    tracker = ExpansionTracker()
    tracker.record(ExpansionRecord(tier="tier_1", strategy_id="XAU", justification="test", approved=True))
    tracker.record(ExpansionRecord(tier="tier_2", strategy_id="EUR", justification="test", approved=True))
    assert len(tracker.get_by_tier("tier_1")) == 1

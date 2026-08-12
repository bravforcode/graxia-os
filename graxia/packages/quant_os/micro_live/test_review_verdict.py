"""Tests for micro-live review verdict."""
from graxia.packages.quant_os.micro_live.review_verdict import MicroLiveVerdict


def test_verdict_eligible():
    v = MicroLiveVerdict()
    evidence = {
        "critical_incidents": 0, "reconciliation_pct": 100,
        "cost_gap_pct": 20, "safety_incidents": 0, "days_run": 60,
    }
    verdict = v.evaluate(evidence)
    assert verdict == "ELIGIBLE_FOR_EXPANSION"


def test_verdict_archive_on_incident():
    v = MicroLiveVerdict()
    evidence = {"critical_incidents": 1}
    verdict = v.evaluate(evidence)
    assert verdict == "ARCHIVE"


def test_verdict_extend_on_short_window():
    v = MicroLiveVerdict()
    evidence = {
        "critical_incidents": 0, "reconciliation_pct": 100,
        "cost_gap_pct": 20, "safety_incidents": 0, "days_run": 10,
    }
    verdict = v.evaluate(evidence)
    assert verdict == "EXTEND_MICRO_LIVE"

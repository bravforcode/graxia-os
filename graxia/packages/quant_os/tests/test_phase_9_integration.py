"""Phase 9 integration tests — controlled micro-live review."""
import pytest

try:
    from graxia.packages.quant_os.canary.review.review_criteria import ReviewChecklist, ReviewOutcome
    from graxia.packages.quant_os.canary.review.review_report import ReviewReport
    _HAS_REVIEW = True
except ImportError:
    _HAS_REVIEW = False

pytestmark = pytest.mark.skipif(not _HAS_REVIEW, reason="Missing module: graxia.packages.quant_os.canary.review (not yet implemented)")


def test_review_checklist_exists():
    """ReviewChecklist must exist."""
    checklist = ReviewChecklist()
    assert checklist is not None


def test_review_outcomes():
    """All review outcomes must be defined."""
    assert ReviewOutcome.ARCHIVE.value == "archive"
    assert ReviewOutcome.RETURN_TO_RESEARCH.value == "return_to_research"
    assert ReviewOutcome.EXTEND_DEMO.value == "extend_demo"
    assert ReviewOutcome.ELIGIBLE_FOR_MICRO_LIVE_CANARY.value == "eligible_for_micro_live_canary"


def test_review_checklist_eligible():
    """Checklist must return ELIGIBLE when all pass."""
    checklist = ReviewChecklist(
        backtest_passes_gate=True,
        demo_campaign_passes_gate=True,
        critical_incidents_zero=True,
        protective_stop_verification_100=True,
        reconciliation_accuracy_100=True,
        no_stale_data_trades=True,
        no_risk_budget_breaches=True,
        no_duplicate_submissions=True,
        cost_model_gap_within_tolerance=True,
        strategy_distribution_consistent=True,
        independent_oracle_match=True,
        no_archive_reasons_present=True,
    )
    assert checklist.evaluate() == ReviewOutcome.ELIGIBLE_FOR_MICRO_LIVE_CANARY


def test_review_checklist_archive():
    """Checklist must return ARCHIVE when archive reasons present."""
    checklist = ReviewChecklist(no_archive_reasons_present=False)
    assert checklist.evaluate() == ReviewOutcome.ARCHIVE


def test_review_report_generate():
    """ReviewReport must generate valid dict."""
    report = ReviewReport(report_id="RPT-001", candidate_id="XAU_LIQSWEEP_LOCKED_001")
    data = report.generate()
    assert data["report_id"] == "RPT-001"
    assert data["candidate_id"] == "XAU_LIQSWEEP_LOCKED_001"
    assert "outcome" in data
    assert "checklist" in data

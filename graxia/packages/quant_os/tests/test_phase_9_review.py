"""Tests for Phase 9 — Review framework."""

import pytest

try:
    from graxia.packages.quant_os.canary.review.review_criteria import (
        ArchiveReason,
        ReviewChecklist,
        ReviewOutcome,
    )
    from graxia.packages.quant_os.canary.review.review_report import ReviewReport
except ImportError:
    pytest.skip(
        "canary.review.review_criteria module not available",
        allow_module_level=True,
    )


def test_review_checklist_default():
    checklist = ReviewChecklist()
    assert checklist.evaluate() == ReviewOutcome.ARCHIVE


def test_review_checklist_eligible():
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
    checklist = ReviewChecklist(no_archive_reasons_present=False)
    assert checklist.evaluate() == ReviewOutcome.ARCHIVE


def test_review_checklist_extend_demo():
    checklist = ReviewChecklist(
        backtest_passes_gate=True,
        demo_campaign_passes_gate=True,
        no_archive_reasons_present=True,
        critical_incidents_zero=False,
    )
    assert checklist.evaluate() == ReviewOutcome.EXTEND_DEMO


def test_review_report_generate():
    report = ReviewReport(report_id="R001", candidate_id="C001")
    result = report.generate()
    assert result["report_id"] == "R001"
    assert result["candidate_id"] == "C001"
    assert result["outcome"] == ReviewOutcome.RETURN_TO_RESEARCH.value
    assert "checklist" in result
    assert isinstance(result["archive_reasons"], list)

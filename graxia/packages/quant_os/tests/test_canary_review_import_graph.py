from graxia.packages.quant_os.canary.review import ReviewChecklist, ReviewOutcome, ReviewReport
from graxia.packages.quant_os.canary.review.review_criteria import ArchiveReason


def test_canary_review_import_graph_exports_phase9_symbols() -> None:
    checklist = ReviewChecklist(
        backtest_passes_gate=True,
        demo_campaign_passes_gate=True,
        no_archive_reasons_present=True,
    )
    report = ReviewReport(report_id="G0A-IMPORT", candidate_id="XAU_LIQSWEEP_LOCKED_001", checklist=checklist)
    generated = report.generate()

    assert ReviewOutcome.ELIGIBLE_FOR_MICRO_LIVE_CANARY.value == "eligible_for_micro_live_canary"
    assert ArchiveReason.RISK_BUDGETS_EXCEEDED.value == "risk_budgets_exceeded"
    assert generated["candidate_id"] == "XAU_LIQSWEEP_LOCKED_001"


def test_canary_review_import_graph_covers_outcome_and_archive_reason_matrix() -> None:
    extend_demo_checklist = ReviewChecklist(
        backtest_passes_gate=True,
        demo_campaign_passes_gate=True,
        no_archive_reasons_present=True,
        no_risk_budget_breaches=False,
    )
    archive_checklist = ReviewChecklist(no_archive_reasons_present=False)

    assert extend_demo_checklist.evaluate() == ReviewOutcome.EXTEND_DEMO
    assert ArchiveReason.RISK_BUDGETS_EXCEEDED in extend_demo_checklist.archive_reasons()
    assert ReviewReport(
        report_id="G0A-RETURN",
        candidate_id="XAU_LIQSWEEP_LOCKED_001",
        checklist=archive_checklist,
    ).generate()["outcome"] == ReviewOutcome.RETURN_TO_RESEARCH.value

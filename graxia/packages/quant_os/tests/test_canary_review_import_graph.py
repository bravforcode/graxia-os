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

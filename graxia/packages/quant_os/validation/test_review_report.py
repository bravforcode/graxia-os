"""Tests for review report."""
from graxia.packages.quant_os.validation.review_report import ReviewReport, ReviewReportGenerator


def test_report_creates():
    report = ReviewReport(strategy_id="XAU_LIQSWEEP", decision="ELIGIBLE_FOR_MICRO_LIVE")
    assert report.strategy_id == "XAU_LIQSWEEP"


def test_report_markdown():
    report = ReviewReport(
        strategy_id="XAU_LIQSWEEP",
        decision="ELIGIBLE_FOR_MICRO_LIVE",
        blockers=[],
        evidence_summary={"trades": 150},
    )
    md = report.to_markdown()
    assert "Promotion Review Report" in md
    assert "XAU_LIQSWEEP" in md


def test_report_generator():
    gen = ReviewReportGenerator()
    report = gen.generate(
        "XAU_LIQSWEEP", "EXTEND_DEMO", ["insufficient_sample"],
        {"trades": 50}, "extend demo for more evidence",
    )
    assert report.decision == "EXTEND_DEMO"
    assert len(report.blockers) == 1

"""Phase BE-P11 integration tests — promotion review."""
from graxia.packages.quant_os.validation.promotion_review import (
    PromotionReviewer, ReviewInput, PromotionDecision
)
from graxia.packages.quant_os.validation.evidence_pack import EvidencePack
from graxia.packages.quant_os.validation.auto_blockers import AutoBlockerChecker
from graxia.packages.quant_os.validation.review_report import ReviewReport, ReviewReportGenerator


def test_full_review_eligible():
    reviewer = PromotionReviewer()
    inputs = ReviewInput(
        strategy_id="XAU_LIQSWEEP",
        historical_validation={"trade_count": 150, "needs_retuning": False},
        demo_report={"unprotected_positions": 0, "reconciliation_pct": 100},
        cost_calibration={"gap_pct": 20},
        contract_evidence={"broker_identity_locked": True},
        oracle_comparison={"divergence_unresolved": False},
    )
    result = reviewer.decide(inputs)
    assert result.decision == PromotionDecision.ELIGIBLE_FOR_MICRO_LIVE
    assert len(result.blockers) == 0


def test_evidence_pack_complete():
    pack = EvidencePack()
    evidence = {item[0]: {} for item in pack.REQUIRED_ITEMS}
    pack.build(evidence)
    assert pack.is_complete()


def test_auto_blockers_all_clear():
    checker = AutoBlockerChecker()
    context = {
        "critical_incidents": 0, "unprotected_positions": 0,
        "reconciliation_pct": 100, "cost_gap_pct": 20,
        "needs_retuning": False, "broker_identity_locked": True,
        "trade_count": 150, "oracle_divergence": False,
    }
    checker.check(context)
    assert checker.summary()["clear"]


def test_review_report_generation():
    gen = ReviewReportGenerator()
    report = gen.generate(
        "XAU_LIQSWEEP", "ELIGIBLE_FOR_MICRO_LIVE", [],
        {"trades": 150, "reconciliation": "100%"},
    )
    md = report.to_markdown()
    assert "ELIGIBLE_FOR_MICRO_LIVE" in md


def test_full_review_with_blockers():
    reviewer = PromotionReviewer()
    inputs = ReviewInput(
        strategy_id="XAU_LIQSWEEP",
        incident_register={"critical_incidents": 1},
        demo_report={"unprotected_positions": 0, "reconciliation_pct": 100},
    )
    result = reviewer.decide(inputs)
    assert result.decision == PromotionDecision.RETURN_TO_RESEARCH
    assert len(result.blockers) > 0

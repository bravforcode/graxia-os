"""Tests for promotion review."""
from graxia.packages.quant_os.validation.promotion_review import (
    PromotionReviewer, ReviewInput, PromotionDecision
)


def test_reviewer_creates():
    reviewer = PromotionReviewer()
    assert reviewer is not None


def test_reviewer_eligible_for_micro_live():
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


def test_reviewer_returns_to_research():
    reviewer = PromotionReviewer()
    inputs = ReviewInput(
        strategy_id="XAU_LIQSWEEP",
        incident_register={"critical_incidents": 1},
    )
    result = reviewer.decide(inputs)
    assert result.decision == PromotionDecision.RETURN_TO_RESEARCH
    assert "unresolved_critical_incidents" in result.blockers


def test_reviewer_extends_demo():
    reviewer = PromotionReviewer()
    inputs = ReviewInput(
        strategy_id="XAU_LIQSWEEP",
        historical_validation={"trade_count": 50},  # insufficient
        demo_report={"days_run": 5},
        contract_evidence={"broker_identity_locked": True},
    )
    result = reviewer.decide(inputs)
    assert result.decision == PromotionDecision.EXTEND_DEMO


def test_reviewer_multiple_blockers():
    reviewer = PromotionReviewer()
    inputs = ReviewInput(
        strategy_id="XAU_LIQSWEEP",
        incident_register={"critical_incidents": 2},
        demo_report={"unprotected_positions": 1, "reconciliation_pct": 95},
        cost_calibration={"gap_pct": 80},
    )
    result = reviewer.decide(inputs)
    assert len(result.blockers) >= 3

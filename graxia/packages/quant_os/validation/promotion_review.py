"""Phase BE-P11 — Promotion review decision engine."""
from dataclasses import dataclass, field
from datetime import datetime, timezone


class PromotionDecision:
    ARCHIVE_NO_EDGE = "ARCHIVE_NO_EDGE"
    RETURN_TO_RESEARCH = "RETURN_TO_RESEARCH"
    EXTEND_DEMO = "EXTEND_DEMO"
    ELIGIBLE_FOR_MICRO_LIVE = "ELIGIBLE_FOR_GUARDED_MICRO_LIVE_REVIEW"


@dataclass
class ReviewInput:
    strategy_id: str = ""
    historical_validation: dict = field(default_factory=dict)
    oracle_comparison: dict = field(default_factory=dict)
    shadow_report: dict = field(default_factory=dict)
    demo_report: dict = field(default_factory=dict)
    incident_register: dict = field(default_factory=dict)
    cost_calibration: dict = field(default_factory=dict)
    risk_adherence: dict = field(default_factory=dict)
    contract_evidence: dict = field(default_factory=dict)
    release_bundle: dict = field(default_factory=dict)


@dataclass
class ReviewResult:
    decision: str
    strategy_id: str
    blockers: list
    review_id: str = ""
    timestamp_utc: str = ""
    rationale: str = ""
    
    def __post_init__(self):
        if not self.review_id:
            self.review_id = f"REVIEW_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()


class PromotionReviewer:
    """Evaluate promotion with automatic blockers."""
    
    def __init__(self):
        self._reviews: list[ReviewResult] = []
    
    def check_blockers(self, inputs: ReviewInput) -> list[str]:
        """Check all automatic blockers."""
        blockers = []
        
        # Unresolved critical incidents
        if inputs.incident_register.get("critical_incidents", 0) > 0:
            blockers.append("unresolved_critical_incidents")
        
        # Unprotected positions
        if inputs.demo_report.get("unprotected_positions", 0) > 0:
            blockers.append("unprotected_positions")
        
        # Reconciliation mismatch
        if inputs.demo_report.get("reconciliation_pct", 100) < 100:
            blockers.append("reconciliation_mismatch")
        
        # Cost-model gap beyond threshold
        if inputs.cost_calibration.get("gap_pct", 0) > 50:
            blockers.append("cost_model_gap")
        
        # Strategy needs retuning
        if inputs.historical_validation.get("needs_retuning", False):
            blockers.append("needs_retuning")
        
        # Broker identity not locked
        if not inputs.contract_evidence.get("broker_identity_locked", False):
            blockers.append("broker_identity_not_locked")
        
        # Insufficient sample
        if inputs.historical_validation.get("trade_count", 0) < 100:
            blockers.append("insufficient_sample")
        
        # Oracle divergence unresolved
        if inputs.oracle_comparison.get("divergence_unresolved", False):
            blockers.append("oracle_divergence_unresolved")
        
        return blockers
    
    def decide(self, inputs: ReviewInput) -> ReviewResult:
        """Make promotion decision."""
        blockers = self.check_blockers(inputs)
        
        if blockers:
            # Check if extend is possible
            can_extend = (
                inputs.demo_report.get("days_run", 0) > 0 and
                not any(b in blockers for b in [
                    "unresolved_critical_incidents",
                    "unprotected_positions",
                    "broker_identity_not_locked",
                ])
            )
            
            decision = PromotionDecision.EXTEND_DEMO if can_extend else PromotionDecision.RETURN_TO_RESEARCH
            rationale = f"blockers: {', '.join(blockers)}"
        else:
            # No blockers - check if eligible for micro-live
            if inputs.historical_validation.get("trade_count", 0) >= 100:
                decision = PromotionDecision.ELIGIBLE_FOR_MICRO_LIVE
                rationale = "all gates passed, sufficient sample"
            else:
                decision = PromotionDecision.EXTEND_DEMO
                rationale = "insufficient sample, extend demo"
        
        result = ReviewResult(
            decision=decision,
            strategy_id=inputs.strategy_id,
            blockers=blockers,
            rationale=rationale,
        )
        self._reviews.append(result)
        return result
    
    def get_reviews(self) -> list[ReviewResult]:
        return self._reviews.copy()
    
    def get_latest(self) -> ReviewResult | None:
        return self._reviews[-1] if self._reviews else None

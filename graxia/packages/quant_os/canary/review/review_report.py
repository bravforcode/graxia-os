"""Phase 9 review report generator."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .review_criteria import ArchiveReason, ReviewChecklist, ReviewOutcome


@dataclass
class ReviewReport:
    report_id: str
    candidate_id: str
    checklist: ReviewChecklist = field(default_factory=ReviewChecklist)
    operator_notes: str = ""

    def _resolved_outcome(self) -> ReviewOutcome:
        outcome = self.checklist.evaluate()
        if outcome == ReviewOutcome.ARCHIVE and not self.checklist.has_demo_readiness_signal():
            return ReviewOutcome.RETURN_TO_RESEARCH
        return outcome

    def generate(self) -> dict:
        outcome = self._resolved_outcome()
        archive_reasons = [reason.value for reason in self.checklist.archive_reasons()]
        return {
            "report_id": self.report_id,
            "candidate_id": self.candidate_id,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "outcome": outcome.value,
            "checklist": {
                "backtest_passes_gate": self.checklist.backtest_passes_gate,
                "demo_campaign_passes_gate": self.checklist.demo_campaign_passes_gate,
                "critical_incidents_zero": self.checklist.critical_incidents_zero,
                "protective_stop_verification_100": self.checklist.protective_stop_verification_100,
                "reconciliation_accuracy_100": self.checklist.reconciliation_accuracy_100,
                "no_stale_data_trades": self.checklist.no_stale_data_trades,
                "no_risk_budget_breaches": self.checklist.no_risk_budget_breaches,
                "no_duplicate_submissions": self.checklist.no_duplicate_submissions,
                "cost_model_gap_within_tolerance": self.checklist.cost_model_gap_within_tolerance,
                "strategy_distribution_consistent": self.checklist.strategy_distribution_consistent,
                "independent_oracle_match": self.checklist.independent_oracle_match,
                "no_archive_reasons_present": self.checklist.no_archive_reasons_present,
            },
            "archive_reasons": archive_reasons,
            "operator_notes": self.operator_notes,
        }

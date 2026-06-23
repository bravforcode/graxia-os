"""Phase 9 review criteria for guarded micro-live promotion decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ReviewOutcome(Enum):
    ARCHIVE = "archive"
    RETURN_TO_RESEARCH = "return_to_research"
    EXTEND_DEMO = "extend_demo"
    ELIGIBLE_FOR_MICRO_LIVE_CANARY = "eligible_for_micro_live_canary"


class ArchiveReason(Enum):
    CHECKLIST_INCOMPLETE = "checklist_incomplete"
    RISK_BUDGETS_EXCEEDED = "risk_budgets_exceeded"
    MANUAL_ARCHIVE_TRIGGER = "manual_archive_trigger"


@dataclass(frozen=True)
class ReviewChecklist:
    backtest_passes_gate: bool = False
    demo_campaign_passes_gate: bool = False
    critical_incidents_zero: bool = False
    protective_stop_verification_100: bool = False
    reconciliation_accuracy_100: bool = False
    no_stale_data_trades: bool = False
    no_risk_budget_breaches: bool = False
    no_duplicate_submissions: bool = False
    cost_model_gap_within_tolerance: bool = False
    strategy_distribution_consistent: bool = False
    independent_oracle_match: bool = False
    no_archive_reasons_present: bool = False

    def is_fully_eligible(self) -> bool:
        return all(
            (
                self.backtest_passes_gate,
                self.demo_campaign_passes_gate,
                self.critical_incidents_zero,
                self.protective_stop_verification_100,
                self.reconciliation_accuracy_100,
                self.no_stale_data_trades,
                self.no_risk_budget_breaches,
                self.no_duplicate_submissions,
                self.cost_model_gap_within_tolerance,
                self.strategy_distribution_consistent,
                self.independent_oracle_match,
                self.no_archive_reasons_present,
            )
        )

    def has_demo_readiness_signal(self) -> bool:
        return self.backtest_passes_gate and self.demo_campaign_passes_gate

    def archive_reasons(self) -> list[ArchiveReason]:
        reasons: list[ArchiveReason] = []
        if not self.no_archive_reasons_present:
            reasons.append(ArchiveReason.MANUAL_ARCHIVE_TRIGGER)
        if self.has_demo_readiness_signal() and not self.no_risk_budget_breaches:
            reasons.append(ArchiveReason.RISK_BUDGETS_EXCEEDED)
        if not self.has_demo_readiness_signal():
            reasons.append(ArchiveReason.CHECKLIST_INCOMPLETE)
        return reasons

    def evaluate(self) -> ReviewOutcome:
        if self.is_fully_eligible():
            return ReviewOutcome.ELIGIBLE_FOR_MICRO_LIVE_CANARY
        if not self.no_archive_reasons_present:
            return ReviewOutcome.ARCHIVE
        if self.has_demo_readiness_signal():
            return ReviewOutcome.EXTEND_DEMO
        return ReviewOutcome.ARCHIVE

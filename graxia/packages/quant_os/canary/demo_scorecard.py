"""Phase 8 — Demo campaign scorecard."""
from dataclasses import dataclass, field


@dataclass
class DemoScorecard:
    order_intent_count: int = 0
    order_submission_count: int = 0
    broker_rejection_count: int = 0
    broker_rejection_reasons: list = field(default_factory=list)
    fill_latency_ms: float = 0
    expected_vs_observed_entry_deviation: float = 0
    expected_vs_observed_exit_deviation: float = 0
    spread_distribution: list = field(default_factory=list)
    slippage_distribution: list = field(default_factory=list)
    commission_swap_reconciliation: float = 0
    protective_stop_verification_rate_pct: float = 0
    position_deal_reconciliation_rate_pct: float = 0
    stale_data_trades: int = 0
    risk_limit_breaches: int = 0
    critical_incidents: int = 0
    model_vs_demo_pnl_gap: float = 0

    def evaluate(self) -> dict:
        """Evaluate scorecard against promotion gates."""
        issues = []

        if self.critical_incidents > 0:
            issues.append(f"CRITICAL_INCIDENTS: {self.critical_incidents}")

        if self.stale_data_trades > 0:
            issues.append(f"STALE_DATA_TRADES: {self.stale_data_trades}")

        if self.risk_limit_breaches > 0:
            issues.append(f"RISK_LIMIT_BREACHES: {self.risk_limit_breaches}")

        if self.protective_stop_verification_rate_pct < 100:
            issues.append(f"PROTECTIVE_STOP_VERIFICATION: {self.protective_stop_verification_rate_pct}%")

        if self.position_deal_reconciliation_rate_pct < 100:
            issues.append(f"RECONCILIATION_RATE: {self.position_deal_reconciliation_rate_pct}%")

        return {
            "passed": len(issues) == 0,
            "issues": issues,
            "verdict": "PASS" if len(issues) == 0 else "FAIL",
        }

"""Phase BE-P10 — Weekly campaign reporting."""
from dataclasses import dataclass


@dataclass
class WeeklyReport:
    week_start: str = ""
    week_end: str = ""
    backtest_demo_gap_pct: float = 0.0
    cost_model_drift_pct: float = 0.0
    rule_exceptions: int = 0
    risk_limit_breaches: int = 0
    reconciliation_accuracy_pct: float = 100.0
    unresolved_incidents: int = 0
    total_signals: int = 0
    total_orders: int = 0
    total_fills: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}

    def to_markdown(self) -> str:
        lines = [
            f"# Weekly Report: {self.week_start} to {self.week_end}",
            "",
            f"**Backtest-Demo Gap:** {self.backtest_demo_gap_pct:.1f}%",
            f"**Cost Model Drift:** {self.cost_model_drift_pct:.1f}%",
            f"**Rule Exceptions:** {self.rule_exceptions}",
            f"**Risk Limit Breaches:** {self.risk_limit_breaches}",
            f"**Reconciliation Accuracy:** {self.reconciliation_accuracy_pct:.1f}%",
            f"**Unresolved Incidents:** {self.unresolved_incidents}",
            f"**Total Signals:** {self.total_signals}",
            f"**Total Orders:** {self.total_orders}",
            f"**Win Rate:** {self.win_rate:.1f}%",
            f"**Profit Factor:** {self.profit_factor:.2f}",
        ]
        return "\n".join(lines)

    def evaluate(self) -> tuple[bool, list[str]]:
        """Evaluate against exit gate criteria."""
        issues = []
        if self.unresolved_incidents > 0:
            issues.append(f"unresolved_incidents={self.unresolved_incidents}")
        if self.reconciliation_accuracy_pct < 100:
            issues.append(f"reconciliation_accuracy={self.reconciliation_accuracy_pct}%")
        if self.risk_limit_breaches > 0:
            issues.append(f"risk_limit_breaches={self.risk_limit_breaches}")
        if self.backtest_demo_gap_pct > 50:
            issues.append(f"backtest_demo_gap={self.backtest_demo_gap_pct}%")
        return len(issues) == 0, issues

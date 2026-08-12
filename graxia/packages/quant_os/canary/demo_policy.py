"""Phase 7 — Demo canary policy."""
from dataclasses import dataclass, field


@dataclass
class DemoCanaryPolicy:
    account_mode: str = "DEMO_ONLY"
    symbols: list = field(default_factory=lambda: ["XAUUSD"])
    max_open_positions: int = 1
    max_orders_per_day: int = 3
    risk_per_trade_bps: int = 10
    max_daily_loss_bps: int = 50
    max_weekly_loss_bps: int = 150
    max_total_drawdown_bps: int = 300
    first_orders_require_human_approval: int = 20
    auto_increase_risk: bool = False
    auto_add_symbol: bool = False
    auto_change_parameters: bool = False

    def validate(self) -> tuple[bool, list[str]]:
        issues = []
        if self.account_mode != "DEMO_ONLY":
            issues.append(f"account_mode must be DEMO_ONLY, got {self.account_mode}")
        if self.auto_increase_risk:
            issues.append("auto_increase_risk must be False")
        if self.auto_add_symbol:
            issues.append("auto_add_symbol must be False")
        if self.auto_change_parameters:
            issues.append("auto_change_parameters must be False")
        return len(issues) == 0, issues

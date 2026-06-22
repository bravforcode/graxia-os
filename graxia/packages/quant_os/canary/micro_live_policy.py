"""Phase 10 — Micro-live canary policy. First point where real capital can be considered."""
from dataclasses import dataclass, field


@dataclass
class MicroLivePolicy:
    """Stricter than demo. First point where real capital can be considered."""
    max_symbols: int = 1
    max_open_positions: int = 1
    max_orders_per_day: int = 1
    risk_per_trade_bps: int = 5
    max_daily_loss_bps: int = 20
    max_weekly_loss_bps: int = 50
    max_total_drawdown_bps: int = 100
    no_compounding: bool = True
    no_parameter_changes: bool = True
    no_new_data_source: bool = True
    no_second_broker: bool = True
    emergency_kill_switch: bool = True

    def validate(self) -> tuple[bool, list[str]]:
        issues = []
        if self.max_symbols > 1:
            issues.append(f"max_symbols must be 1, got {self.max_symbols}")
        if self.max_open_positions > 1:
            issues.append(f"max_open_positions must be 1, got {self.max_open_positions}")
        if self.max_orders_per_day > 1:
            issues.append(f"max_orders_per_day must be 1, got {self.max_orders_per_day}")
        if self.risk_per_trade_bps > 5:
            issues.append(f"risk_per_trade_bps must be <= 5, got {self.risk_per_trade_bps}")
        if self.max_daily_loss_bps > 20:
            issues.append(f"max_daily_loss_bps must be <= 20, got {self.max_daily_loss_bps}")
        if self.max_weekly_loss_bps > 50:
            issues.append(f"max_weekly_loss_bps must be <= 50, got {self.max_weekly_loss_bps}")
        if self.max_total_drawdown_bps > 100:
            issues.append(f"max_total_drawdown_bps must be <= 100, got {self.max_total_drawdown_bps}")
        if not self.emergency_kill_switch:
            issues.append("emergency_kill_switch must be True")
        return len(issues) == 0, issues

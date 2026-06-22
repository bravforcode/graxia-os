"""Phase BE-P12 — Micro-live policy."""
from dataclasses import dataclass


@dataclass
class MicroLivePolicy:
    """Micro-live constraints per BE-P12 spec."""
    symbol_count: int = 1
    strategy_count: int = 1
    max_open_positions: int = 1
    fixed_volume: str = "smallest_allowed"
    risk_per_trade_bps: int = 10
    max_daily_loss_bps: int = 50
    max_weekly_loss_bps: int = 150
    max_total_drawdown_bps: int = 300
    max_orders_per_day: int = 3
    compounding: str = "forbidden"
    auto_parameter_tuning: str = "forbidden"
    auto_strategy_switching: str = "forbidden"
    human_session_enablement: str = "required"
    kill_switch: str = "required"
    
    def validate(self) -> tuple[bool, list[str]]:
        issues = []
        if self.symbol_count > 1:
            issues.append(f"symbol_count must be 1, got {self.symbol_count}")
        if self.max_open_positions > 1:
            issues.append(f"max_open_positions must be 1")
        if self.risk_per_trade_bps > 10:
            issues.append(f"risk_per_trade_bps must be <= 10")
        if self.compounding != "forbidden":
            issues.append("compounding must be forbidden")
        if self.auto_parameter_tuning != "forbidden":
            issues.append("auto_parameter_tuning must be forbidden")
        if self.auto_strategy_switching != "forbidden":
            issues.append("auto_strategy_switching must be forbidden")
        if self.human_session_enablement != "required":
            issues.append("human_session_enablement must be required")
        if self.kill_switch != "required":
            issues.append("kill_switch must be required")
        return len(issues) == 0, issues
    
    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}

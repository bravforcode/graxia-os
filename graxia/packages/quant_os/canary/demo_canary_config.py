"""Phase BE-P9 — Demo canary configuration."""
from dataclasses import dataclass


@dataclass
class DemoCanaryConfig:
    """Canary policy per BE-P9 spec."""
    account_mode: str = "DEMO"
    symbols: list = None
    strategies: list = None
    max_open_positions: int = 1
    max_orders_per_day: int = 3
    risk_per_trade_bps: int = 10
    max_daily_loss_bps: int = 50
    max_weekly_loss_bps: int = 150
    max_total_drawdown_bps: int = 300
    require_manual_enable_each_session: bool = True
    require_stop_loss: bool = True
    require_take_profit_or_time_stop: bool = True
    blind_retry_allowed: bool = False
    kill_switch_enabled: bool = True

    def __post_init__(self):
        if self.symbols is None:
            self.symbols = ["XAUUSD"]
        if self.strategies is None:
            self.strategies = ["one_approved_strategy_only"]

    def validate(self) -> tuple[bool, list[str]]:
        issues = []
        if self.account_mode != "DEMO":
            issues.append(f"account_mode must be DEMO, got {self.account_mode}")
        if len(self.symbols) > 1:
            issues.append(f"max 1 symbol, got {len(self.symbols)}")
        if self.max_open_positions > 1:
            issues.append(f"max_open_positions must be 1, got {self.max_open_positions}")
        if self.risk_per_trade_bps > 10:
            issues.append(f"risk_per_trade_bps must be <= 10, got {self.risk_per_trade_bps}")
        if not self.kill_switch_enabled:
            issues.append("kill_switch_enabled must be True")
        if self.blind_retry_allowed:
            issues.append("blind_retry_allowed must be False")
        return len(issues) == 0, issues

    def to_dict(self) -> dict:
        return {
            "account_mode": self.account_mode,
            "symbols": self.symbols,
            "strategies": self.strategies,
            "max_open_positions": self.max_open_positions,
            "max_orders_per_day": self.max_orders_per_day,
            "risk_per_trade_bps": self.risk_per_trade_bps,
            "max_daily_loss_bps": self.max_daily_loss_bps,
            "max_weekly_loss_bps": self.max_weekly_loss_bps,
            "max_total_drawdown_bps": self.max_total_drawdown_bps,
            "kill_switch_enabled": self.kill_switch_enabled,
        }

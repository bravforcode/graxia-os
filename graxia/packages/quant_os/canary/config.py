from dataclasses import dataclass, field
from typing import Optional
import yaml
import json
import hashlib

@dataclass
class CanaryConfig:
    """Canary configuration — one broker, one symbol, one strategy, demo only."""
    execution_enabled: bool = False
    account_mode_required: str = "DEMO"
    allowed_symbols: list[str] = field(default_factory=lambda: ["XAUUSD"])
    allowed_strategies: list[str] = field(default_factory=lambda: ["liquidity_sweep_locked_version"])
    max_open_positions: int = 1
    max_orders_per_day: int = 3
    risk_per_trade_bps: int = 10
    max_daily_loss_bps: int = 50
    max_weekly_loss_bps: int = 150
    max_total_drawdown_bps: int = 300
    require_stop_loss: bool = True
    require_take_profit_or_time_stop: bool = True
    require_pre_trade_order_check: bool = True
    require_post_fill_stop_verification: bool = True
    require_reconciliation: bool = True
    require_manual_session_enable: bool = True
    auto_resume_after_kill_switch: bool = False

    def validate(self) -> tuple[bool, list[str]]:
        issues = []
        if self.account_mode_required != "DEMO":
            issues.append(f"ACCOUNT_MODE_MUST_BE_DEMO:{self.account_mode_required}")
        if self.max_open_positions > 3:
            issues.append(f"MAX_POSITIONS_TOO_HIGH:{self.max_open_positions}")
        if self.max_orders_per_day > 10:
            issues.append(f"MAX_ORDERS_TOO_HIGH:{self.max_orders_per_day}")
        if self.risk_per_trade_bps > 50:
            issues.append(f"RISK_TOO_HIGH:{self.risk_per_trade_bps}")
        if self.auto_resume_after_kill_switch:
            issues.append("AUTO_RESUME_FORBIDDEN")
        return len(issues) == 0, issues

    def check_symbol(self, symbol: str) -> tuple[bool, str]:
        if symbol not in self.allowed_symbols:
            return False, f"SYMBOL_NOT_ALLOWED:{symbol}"
        return True, "ALLOWED"

    def check_strategy(self, strategy_id: str) -> tuple[bool, str]:
        if strategy_id not in self.allowed_strategies:
            return False, f"STRATEGY_NOT_ALLOWED:{strategy_id}"
        return True, "ALLOWED"

    def fingerprint(self) -> str:
        data = json.dumps({
            "execution_enabled": self.execution_enabled,
            "max_open_positions": self.max_open_positions,
            "risk_per_trade_bps": self.risk_per_trade_bps,
            "max_daily_loss_bps": self.max_daily_loss_bps,
        }, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()

    def to_yaml(self) -> str:
        return yaml.dump({
            "demo_canary": {
                "execution_enabled": self.execution_enabled,
                "account_mode_required": self.account_mode_required,
                "allowed_symbols": self.allowed_symbols,
                "allowed_strategies": self.allowed_strategies,
                "max_open_positions": self.max_open_positions,
                "max_orders_per_day": self.max_orders_per_day,
                "risk_per_trade_bps": self.risk_per_trade_bps,
                "max_daily_loss_bps": self.max_daily_loss_bps,
                "max_weekly_loss_bps": self.max_weekly_loss_bps,
                "max_total_drawdown_bps": self.max_total_drawdown_bps,
                "require_stop_loss": self.require_stop_loss,
                "require_take_profit_or_time_stop": self.require_take_profit_or_time_stop,
                "require_pre_trade_order_check": self.require_pre_trade_order_check,
                "require_post_fill_stop_verification": self.require_post_fill_stop_verification,
                "require_reconciliation": self.require_reconciliation,
                "require_manual_session_enable": self.require_manual_session_enable,
                "auto_resume_after_kill_switch": self.auto_resume_after_kill_switch,
            }
        }, default_flow_style=False)

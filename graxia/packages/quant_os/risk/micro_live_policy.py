"""Micro-live risk policy — tighter than default RiskPolicy for guarded live testing.

Canonical location.  Other packages (canary, micro_live) re-export from here.
"""

from dataclasses import dataclass

from .risk_policy import RiskPolicy


@dataclass(frozen=True)
class MicroLivePolicyConfig:
    """Standalone config (no RiskPolicy inheritance) for legacy callers."""

    max_symbols: int = 1
    max_open_positions: int = 1
    max_orders_per_day: int = 1
    risk_per_trade_bps: int = 5
    max_daily_loss_bps: int = 20
    max_weekly_loss_bps: int = 50
    max_total_drawdown_bps: int = 100
    emergency_kill_switch: bool = True
    no_compounding: bool = True
    no_parameter_changes: bool = True
    no_new_data_source: bool = True
    no_second_broker: bool = True


@dataclass(frozen=True)
class MicroLivePolicy(RiskPolicy):
    """Tightened risk policy for micro-live. Inherits RiskPolicy, overrides defaults."""

    risk_per_trade_bps: int = 5  # 0.05% (half of standard)
    max_daily_loss_bps: int = 20  # 0.20% (half of standard)
    max_weekly_loss_bps: int = 50  # 0.50% (third of standard)
    max_total_drawdown_bps: int = 100  # 1.00% (third of standard)
    max_open_positions: int = 1  # Single position only
    max_orders_per_day: int = 1  # Conservative
    require_stop_loss: bool = True
    require_contract_snapshot: bool = True
    require_order_check: bool = True
    fail_closed: bool = True
    strict_mtf: bool = True

    # Micro-live specific constraints
    allow_compounding: bool = False
    allow_increase_after_wins: bool = False
    require_human_session_enable: bool = True
    auto_resume_after_kill_switch: bool = False
    account_mode: str = "DEMO"
    allowed_symbols: tuple = ("XAUUSD",)

    # --- Backward-compatible aliases (canary / micro_live consumers) ---
    max_symbols: int = 1
    emergency_kill_switch: bool = True
    symbol_count: int = 1
    strategy_count: int = 1
    fixed_volume: str = "smallest_allowed"
    compounding: str = "forbidden"
    auto_parameter_tuning: str = "forbidden"
    auto_strategy_switching: str = "forbidden"
    human_session_enablement: str = "required"
    kill_switch: str = "required"
    no_compounding: bool = True
    no_parameter_changes: bool = True
    no_new_data_source: bool = True
    no_second_broker: bool = True

    def validate(self) -> tuple[bool, list[str]]:
        """Validate micro-live constraints. Returns (ok, issues)."""
        issues = []

        if self.max_symbols > 1:
            issues.append(f"max_symbols must be 1, got {self.max_symbols}")
        if self.symbol_count > 1:
            issues.append(f"symbol_count must be 1, got {self.symbol_count}")
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
        """Export all fields as a plain dict."""
        return {k: v for k, v in self.__dict__.items()}

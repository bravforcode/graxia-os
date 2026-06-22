"""Micro-live risk policy — tighter than default RiskPolicy for guarded live testing."""

from dataclasses import dataclass
from .risk_policy import RiskPolicy


@dataclass(frozen=True)
class MicroLivePolicy(RiskPolicy):
    """Tightened risk policy for micro-live. Inherits RiskPolicy, overrides defaults."""
    risk_per_trade_bps: int = 5          # 0.05% (half of standard)
    max_daily_loss_bps: int = 20         # 0.20% (half of standard)
    max_weekly_loss_bps: int = 50        # 0.50% (third of standard)
    max_total_drawdown_bps: int = 100    # 1.00% (third of standard)
    max_open_positions: int = 1          # Single position only
    max_orders_per_day: int = 2          # Conservative
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

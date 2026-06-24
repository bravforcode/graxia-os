"""
Trading mode configuration — PAPER | DEMO | LIVE.
Single source of truth for all mode-dependent behavior.

PAPER:  No MT5 connection needed. All orders simulated.
DEMO:   MT5 demo account. DRY_RUN_MODE gates real sends.
LIVE:   MT5 live/production. All guards must pass.
"""
from __future__ import annotations
import os
from enum import Enum


class TradingMode(Enum):
    PAPER = "PAPER"
    DEMO = "DEMO"
    LIVE = "LIVE"


def get_trading_mode() -> TradingMode:
    """Read TRADING_MODE from env. Defaults to DEMO (safe)."""
    raw = os.environ.get("TRADING_MODE", "DEMO").strip().upper()
    try:
        return TradingMode(raw)
    except ValueError:
        return TradingMode.DEMO


def is_live() -> bool:
    return get_trading_mode() == TradingMode.LIVE


def is_demo() -> bool:
    return get_trading_mode() == TradingMode.DEMO


def is_paper() -> bool:
    return get_trading_mode() == TradingMode.PAPER


def requires_mt5() -> bool:
    """PAPER mode doesn't need MT5. DEMO and LIVE do."""
    return get_trading_mode() != TradingMode.PAPER


class RiskLimits:
    """Daily risk limits. Read from env with safe defaults.

    ponytail: flat attrs, no config framework. Extend as needed.
    """
    def __init__(self) -> None:
        self.max_daily_loss_pct = float(os.environ.get("RISK_MAX_DAILY_LOSS_PCT", "2.0"))
        self.max_position_size_pct = float(os.environ.get("RISK_MAX_POSITION_SIZE_PCT", "5.0"))
        self.max_consecutive_losses = int(os.environ.get("RISK_MAX_CONSECUTIVE_LOSSES", "3"))
        self.max_daily_trades = int(os.environ.get("RISK_MAX_DAILY_TRADES", "10"))
        self.max_drawdown_pct = float(os.environ.get("RISK_MAX_DRAWDOWN_PCT", "10.0"))

    def to_dict(self) -> dict:
        return {
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "max_position_size_pct": self.max_position_size_pct,
            "max_consecutive_losses": self.max_consecutive_losses,
            "max_daily_trades": self.max_daily_trades,
            "max_drawdown_pct": self.max_drawdown_pct,
        }

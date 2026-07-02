"""Account equity — single source of truth for live and backtest equity.

Bug #5 fix: multiple code paths read equity from different sources:
  - MT5 account_info() in live bots
  - hardcoded defaults in risk engine
  - BacktestConfig.initial_capital in backtests

This module provides:
  - get_account_equity() -> current equity from single canonical source
  - set_account_equity(equity) -> set equity (for backtest / paper init)
  - reset_account_equity() -> clear stored override, fall back to MT5

Thread-safe via module-level lock.
"""

from __future__ import annotations

import threading
from decimal import Decimal
from typing import Optional

# Module-level state
_equity_override: Optional[float] = None
_lock = threading.Lock()


def get_account_equity(mt5=None) -> float:
    """Get current account equity from the canonical source.

    Priority:
    1. If set_account_equity() was called, return that override.
    2. If mt5 module is provided, query MT5 account_info().equity.
    3. Return 0.0 as safe fallback (blocks all trades via risk engine).

    Args:
        mt5: Optional MetaTrader5 module. If None, skips MT5 query.

    Returns:
        Account equity as float. 0.0 if unavailable.
    """
    with _lock:
        if _equity_override is not None:
            return _equity_override

    # Try MT5
    if mt5 is not None:
        try:
            info = mt5.account_info()
            if info is not None:
                return float(info.equity)
        except Exception:
            pass

    return 0.0


def set_account_equity(equity: float) -> None:
    """Set equity override (for backtest / paper trading initialization).

    Args:
        equity: Account equity value. Must be >= 0.
    """
    if equity < 0:
        raise ValueError(f"equity must be >= 0, got {equity}")

    global _equity_override
    with _lock:
        _equity_override = equity


def reset_account_equity() -> None:
    """Clear stored override, fall back to MT5 query."""
    global _equity_override
    with _lock:
        _equity_override = None


def get_account_equity_decimal(mt5=None) -> Decimal:
    """Get current account equity as Decimal for precision-sensitive calculations.

    Same logic as get_account_equity() but returns Decimal.
    """
    return Decimal(str(get_account_equity(mt5)))

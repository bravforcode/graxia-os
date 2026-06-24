"""
Daily risk limit tracker — in-memory, reset on restart.

ponytail: in-memory only. For persistence across restarts, add a SQLite/file store.
"""
from __future__ import annotations
from datetime import date
from typing import Optional

from config.trading_config import RiskLimits


class DailyRiskTracker:
    """Tracks daily trading metrics against configured limits."""

    def __init__(self, limits: Optional[RiskLimits] = None) -> None:
        self._limits = limits or RiskLimits()
        self._today = date.today()
        self._daily_pnl: float = 0.0
        self._trade_count: int = 0
        self._consecutive_losses: int = 0
        self._peak_equity: Optional[float] = None

    def reset_if_new_day(self) -> None:
        """Reset counters if a new trading day has started."""
        today = date.today()
        if today != self._today:
            self._today = today
            self._daily_pnl = 0.0
            self._trade_count = 0
            self._consecutive_losses = 0

    def record_trade(self, pnl: float, equity: Optional[float] = None) -> None:
        """Record a completed trade P&L and update metrics."""
        self._daily_pnl += pnl
        self._trade_count += 1
        if pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0
        if equity is not None:
            if self._peak_equity is None or equity > self._peak_equity:
                self._peak_equity = equity

    @property
    def daily_pnl(self) -> float:
        return self._daily_pnl

    @property
    def trade_count(self) -> int:
        return self._trade_count

    @property
    def consecutive_losses(self) -> int:
        return self._consecutive_losses

    def check_limits(self, equity: float) -> list[str]:
        """Return list of limit violations (empty = all clear)."""
        violations: list[str] = []

        # Daily loss
        daily_loss_pct = (abs(self._daily_pnl) / equity * 100) if equity > 0 and self._daily_pnl < 0 else 0
        if daily_loss_pct > self._limits.max_daily_loss_pct:
            violations.append(f"Daily loss {daily_loss_pct:.1f}% exceeds limit {self._limits.max_daily_loss_pct}%")

        # Trade count
        if self._trade_count >= self._limits.max_daily_trades:
            violations.append(f"Trade count {self._trade_count} >= limit {self._limits.max_daily_trades}")

        # Consecutive losses
        if self._consecutive_losses >= self._limits.max_consecutive_losses:
            violations.append(f"Consecutive losses {self._consecutive_losses} >= limit {self._limits.max_consecutive_losses}")

        # Drawdown
        if self._peak_equity is not None and self._peak_equity > 0:
            dd_pct = (self._peak_equity - equity) / self._peak_equity * 100
            if dd_pct > self._limits.max_drawdown_pct:
                violations.append(f"Drawdown {dd_pct:.1f}% exceeds limit {self._limits.max_drawdown_pct}%")

        return violations

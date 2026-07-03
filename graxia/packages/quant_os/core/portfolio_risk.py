"""
Portfolio Risk Aggregation — Aggregate risk across all open positions.

Checks:
  - Total portfolio exposure (sum of all position risks)
  - Per-symbol concentration (max % of capital in one symbol)
  - Correlation-adjusted risk (highly correlated = double counted)
  - Daily P&L limit
  - Max drawdown check

Usage:
  from core.portfolio_risk import PortfolioRisk
  pr = PortfolioRisk(capital=10000)
  pr.add_position("XAUUSD", risk_dollars=50)
  allowed = pr.can_add("USDJPY", risk_dollars=100)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class Position:
    symbol: str
    direction: str
    entry_price: float
    risk_dollars: float
    size_lots: float
    opened_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class PortfolioRisk:
    """
    Aggregate risk management across all open positions.

    Limits:
      - Max total risk: 5% of capital
      - Max per-symbol: 2% of capital
      - Max correlated risk: 3% (for highly correlated pairs)
      - Daily loss limit: 2% of capital
      - Max drawdown: 10% of capital
    """

    MAX_TOTAL_RISK_PCT = 0.05  # 5% total
    MAX_PER_SYMBOL_PCT = 0.02  # 2% per symbol
    MAX_CORRELATED_PCT = 0.03  # 3% for correlated pairs
    MAX_DAILY_LOSS_PCT = 0.02  # 2% daily loss
    MAX_DRAWDOWN_PCT = 0.10  # 10% max drawdown

    CORRELATED_PAIRS = {
        frozenset({"EURUSD", "GBPUSD"}),  # EUR/GBP correlated
        frozenset({"AUDUSD", "NZDUSD"}),  # AUD/NZD correlated
        frozenset({"XAUUSD", "XAGUSD"}),  # Gold/Silver correlated
    }

    def __init__(self, capital: float = 10000.0):
        self.capital = capital
        self._positions: dict[str, Position] = {}
        self._daily_pnl: float = 0.0
        self._peak_equity: float = capital
        self._current_equity: float = capital

    @property
    def total_risk(self) -> float:
        return sum(p.risk_dollars for p in self._positions.values())

    @property
    def total_risk_pct(self) -> float:
        return self.total_risk / self.capital if self.capital > 0 else 0

    @property
    def daily_loss_pct(self) -> float:
        return abs(self._daily_pnl) / self.capital if self._daily_pnl < 0 else 0

    @property
    def drawdown(self) -> float:
        if self._peak_equity <= 0:
            return 0.0
        return (self._peak_equity - self._current_equity) / self._peak_equity

    def add_position(self, pos: Position) -> None:
        self._positions[pos.symbol] = pos

    def remove_position(self, symbol: str) -> None:
        self._positions.pop(symbol, None)

    def update_pnl(self, pnl: float) -> None:
        self._daily_pnl += pnl
        self._current_equity += pnl
        self._peak_equity = max(self._peak_equity, self._current_equity)

    def reset_daily(self) -> None:
        self._daily_pnl = 0.0

    def _symbol_risk(self, symbol: str) -> float:
        return self._positions.get(
            symbol, Position(symbol="", direction="", entry_price=0, risk_dollars=0, size_lots=0)
        ).risk_dollars

    def _correlated_risk(self, symbol: str) -> float:
        risk = self._symbol_risk(symbol)
        for pair in self.CORRELATED_PAIRS:
            if symbol in pair:
                for other in pair:
                    if other != symbol:
                        risk += self._symbol_risk(other)
        return risk

    def can_add(self, symbol: str, risk_dollars: float) -> dict:
        """
        Check if we can add a new position.

        Returns:
            Dict with allowed: bool, reasons: list[str]
        """
        reasons = []

        # Check total risk
        new_total = self.total_risk + risk_dollars
        if new_total / self.capital > self.MAX_TOTAL_RISK_PCT:
            reasons.append(f"total_risk {new_total/self.capital:.1%} > {self.MAX_TOTAL_RISK_PCT:.0%}")

        # Check per-symbol
        new_symbol = self._symbol_risk(symbol) + risk_dollars
        if new_symbol / self.capital > self.MAX_PER_SYMBOL_PCT:
            reasons.append(f"symbol_risk {new_symbol/self.capital:.1%} > {self.MAX_PER_SYMBOL_PCT:.0%}")

        # Check correlated
        new_correlated = self._correlated_risk(symbol) + risk_dollars
        if new_correlated / self.capital > self.MAX_CORRELATED_PCT:
            reasons.append(f"correlated_risk {new_correlated/self.capital:.1%} > {self.MAX_CORRELATED_PCT:.0%}")

        # Check daily loss
        if self.daily_loss_pct >= self.MAX_DAILY_LOSS_PCT:
            reasons.append(f"daily_loss {self.daily_loss_pct:.1%} >= {self.MAX_DAILY_LOSS_PCT:.0%}")

        # Check drawdown
        if self.drawdown >= self.MAX_DRAWDOWN_PCT:
            reasons.append(f"drawdown {self.drawdown:.1%} >= {self.MAX_DRAWDOWN_PCT:.0%}")

        allowed = len(reasons) == 0
        if not allowed:
            logger.warning("portfolio_risk.blocked", symbol=symbol, reasons=reasons)

        return {"allowed": allowed, "reasons": reasons}

    def get_status(self) -> dict:
        return {
            "capital": self.capital,
            "total_risk": round(self.total_risk, 2),
            "total_risk_pct": f"{self.total_risk_pct:.1%}",
            "open_positions": len(self._positions),
            "daily_pnl": round(self._daily_pnl, 2),
            "drawdown": f"{self.drawdown:.1%}",
            "positions": {s: {"risk": p.risk_dollars, "direction": p.direction} for s, p in self._positions.items()},
        }

"""
Base strategy interface — all strategies implement `generate_signals(df, params)`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd


class Signal:
    """Single trading signal from a strategy."""

    def __init__(
        self,
        timestamp: str,
        direction: int,  # 1=long, -1=short, 0=flat
        confidence: float,  # 0.0-1.0
        entry_price: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        reason: str = "",
        metadata: dict | None = None,
        bar_index: int | None = None,  # index in DataFrame — used for next-bar execution
    ):
        self.timestamp = timestamp
        self.direction = direction
        self.confidence = confidence
        self.entry_price = entry_price
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.reason = reason
        self.metadata = metadata or {}
        self.bar_index = bar_index

    def __repr__(self) -> str:
        d = {1: "LONG", -1: "SHORT", 0: "FLAT"}.get(self.direction, "?")
        return f"Signal({d} @ {self.entry_price:.4f} conf={self.confidence:.2f})"


class StrategyResult:
    """Result of running a strategy over a dataframe."""

    def __init__(
        self,
        signals: list[Signal],
        equity_curve: list[float] | None = None,
        trades: list[dict] | None = None,
        metrics: dict | None = None,
    ):
        self.signals = signals
        self.equity_curve = equity_curve or []
        self.trades = trades or []
        self.metrics = metrics or {}


class BaseStrategy(ABC):
    """Abstract base for all strategies."""

    def __init__(self, strategy_id: str):
        self.strategy_id = strategy_id

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame, params: dict) -> StrategyResult:
        """Generate trading signals from OHLCV data."""
        ...

    def compute_atr(self, df: pd.DataFrame, period: int = 14) -> np.ndarray:
        """Average True Range."""
        high, low, close = df["high"].values, df["low"].values, df["close"].values
        n = len(close)
        atr = np.zeros(n)
        for i in range(1, n):
            tr = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
            atr[i] = (atr[i - 1] * (period - 1) + tr) / period if i >= period else tr
        return atr

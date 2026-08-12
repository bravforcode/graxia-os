"""Correlation provider for cross-asset risk checks."""
import numpy as np
from typing import Protocol


class CorrelationProvider(Protocol):
    def get_correlation(self, symbol_a: str, symbol_b: str) -> float: ...


class RollingCorrelationProvider:
    """Computes rolling correlation from recent price data."""

    def __init__(self, lookback_bars: int = 100):
        self._lookback = lookback_bars
        self._price_cache: dict[str, list[float]] = {}

    def update(self, symbol: str, price: float):
        if symbol not in self._price_cache:
            self._price_cache[symbol] = []
        self._price_cache[symbol].append(price)
        # Keep only lookback
        if len(self._price_cache[symbol]) > self._lookback:
            self._price_cache[symbol] = self._price_cache[symbol][-self._lookback:]

    def get_correlation(self, symbol_a: str, symbol_b: str) -> float:
        prices_a = self._price_cache.get(symbol_a, [])
        prices_b = self._price_cache.get(symbol_b, [])
        if len(prices_a) < 20 or len(prices_b) < 20:
            return 0.0
        # Align lengths
        n = min(len(prices_a), len(prices_b))
        a = np.array(prices_a[-n:])
        b = np.array(prices_b[-n:])
        # Returns correlation
        ret_a = np.diff(a) / a[:-1]
        ret_b = np.diff(b) / b[:-1]
        if len(ret_a) < 10:
            return 0.0
        corr = np.corrcoef(ret_a, ret_b)[0, 1]
        return float(corr) if not np.isnan(corr) else 0.0

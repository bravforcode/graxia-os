"""
Correlation Filter — Reduce exposure when symbols are highly correlated.

If XAUUSD and USDJPY have correlation > 0.7, reduce position size.
If correlation > 0.9, block the trade entirely.

Usage:
  from core.correlation import CorrelationFilter
  cf = CorrelationFilter()
  cf.update("XAUUSD", price_series)
  cf.update("USDJPY", price_series)
  multiplier = cf.get_multiplier("XAUUSD", "USDJPY")
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np
import structlog

logger = structlog.get_logger(__name__)

# Correlation thresholds
HIGH_CORRELATION = 0.7  # Reduce size by 50%
VERY_HIGH_CORRELATION = 0.9  # Block trade entirely
LOOKBACK = 100  # Bars to calculate correlation


class CorrelationFilter:
    """
    Tracks price series per symbol and computes rolling correlation.
    Returns a position multiplier based on correlation with other open positions.
    """

    def __init__(
        self,
        lookback: int = LOOKBACK,
        high_correlation: float = HIGH_CORRELATION,
        very_high_correlation: float = VERY_HIGH_CORRELATION,
    ):
        self._lookback = lookback
        self._high_correlation = high_correlation
        self._very_high_correlation = very_high_correlation
        self._prices: dict[str, list[float]] = defaultdict(list)
        self._open_symbols: set[str] = set()

    def update(self, symbol: str, close_price: float) -> None:
        """Add a new close price for a symbol."""
        self._prices[symbol].append(close_price)
        # Keep bounded
        if len(self._prices[symbol]) > self._lookback * 2:
            self._prices[symbol] = self._prices[symbol][-self._lookback :]

    def set_open(self, symbols: list[str]) -> None:
        """Set which symbols currently have open positions."""
        self._open_symbols = set(symbols)

    def _correlation(self, sym_a: str, sym_b: str) -> float:
        """Compute Pearson correlation between two symbols."""
        prices_a = self._prices.get(sym_a, [])
        prices_b = self._prices.get(sym_b, [])

        min_len = min(len(prices_a), len(prices_b), self._lookback)
        if min_len < 20:
            return 0.0

        a = np.array(prices_a[-min_len:])
        b = np.array(prices_b[-min_len:])

        # Use returns instead of prices for better correlation
        ret_a = np.diff(a) / a[:-1]
        ret_b = np.diff(b) / b[:-1]

        if len(ret_a) < 10:
            return 0.0

        corr = np.corrcoef(ret_a, ret_b)[0, 1]
        if np.isnan(corr):
            return 0.0

        return float(corr)

    def get_multiplier(self, symbol: str, open_symbols: list[str] | None = None) -> float:
        """
        Get position size multiplier based on correlation with open positions.

        Returns:
            1.0 = no correlation (full size)
            0.5 = high correlation (half size)
            0.0 = very high correlation (block trade)
        """
        targets = open_symbols or list(self._open_symbols)
        targets = [s for s in targets if s != symbol]

        if not targets:
            return 1.0

        worst_corr = 0.0
        for target in targets:
            corr = abs(self._correlation(symbol, target))
            worst_corr = max(worst_corr, corr)

        if worst_corr >= self._very_high_correlation:
            logger.warning(
                "correlation.block",
                symbol=symbol,
                correlated_with=targets,
                correlation=worst_corr,
            )
            return 0.0

        if worst_corr >= self._high_correlation:
            logger.info(
                "correlation.reduce",
                symbol=symbol,
                correlation=worst_corr,
                multiplier=0.5,
            )
            return 0.5

        return 1.0

    def get_all_correlations(self) -> dict[tuple[str, str], float]:
        """Get all pairwise correlations (for monitoring)."""
        symbols = list(self._prices.keys())
        result = {}
        for i, a in enumerate(symbols):
            for b in symbols[i + 1 :]:
                corr = self._correlation(a, b)
                result[(a, b)] = round(corr, 4)
        return result

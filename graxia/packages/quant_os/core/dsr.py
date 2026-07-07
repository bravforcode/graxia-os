"""
Unified Deflated Sharpe Ratio interface.
Single source of truth for strategy validation.
"""

from validation.deflated_sharpe import (
    DeflatedSharpeResult,
    MinBTLResult,
    deflated_sharpe_ratio,
    min_backtest_length,
)

__all__ = [
    "deflated_sharpe_ratio",
    "min_backtest_length",
    "DeflatedSharpeResult",
    "MinBTLResult",
]

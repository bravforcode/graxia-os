"""Returns computation with explicit weekend/missing-bar policy.

Provides compute_returns() that handles gaps in trading data correctly,
avoiding the common pitfall of forward-filling returns across weekends
and holidays (which masks true volatility and distorts Sharpe ratios).
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


def compute_returns(
    prices: pd.Series,
    lookback: int = 1,
    fill_method: Optional[str] = None,
) -> pd.Series:
    """Compute returns with explicit missing-bar policy.

    Args:
        prices: Price series (must be sorted by time).
        lookback: Number of periods for return calculation (default 1 = daily).
        fill_method: How to handle missing bars in the price series before
            computing returns. Options:
            - None (default): compute returns on available bars only;
              missing bars produce NaN returns (honest approach).
            - "ffill": forward-fill missing prices, then compute returns.
              WARNING: this masks weekend/holiday volatility gaps.
            - "log_diff": compute log-returns, which are additive across
              time aggregation but still require honest missing-bar handling.

    Returns:
        pd.Series of returns aligned to the same index as prices.

    Design rationale:
        The default (fill_method=None) treats missing bars as missing data,
        not as zero-return days. This is the honest approach for financial
        data where weekends/holidays are not trading days — forward-filling
        prices across gaps would make volatility appear lower than reality
        and inflate Sharpe ratios.
    """
    if not isinstance(prices, pd.Series):
        raise TypeError(f"prices must be pd.Series, got {type(prices)}")

    if len(prices) < lookback + 1:
        return pd.Series(np.nan, index=prices.index, name="returns")

    if fill_method == "ffill":
        prices = prices.ffill()

    if fill_method == "log_diff":
        log_prices = np.log(prices.replace(0, np.nan))
        returns = log_prices.diff(lookback)
    else:
        # Simple percentage return over lookback periods
        returns = prices.pct_change(lookback)

    # Replace inf with NaN (can happen when price goes to 0)
    returns = returns.replace([np.inf, -np.inf], np.nan)

    return returns


def compute_log_returns(prices: pd.Series, lookback: int = 1) -> pd.Series:
    """Convenience: compute log returns (additive, no fill)."""
    return compute_returns(prices, lookback, fill_method="log_diff")

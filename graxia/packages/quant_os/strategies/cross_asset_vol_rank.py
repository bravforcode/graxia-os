"""
Cross-Asset Volatility Rank (CVR) — relative vol value signal.

Trial #1008 in the quant_os edge-search ledger.

ECONOMIC RATIONALE
==================
Volatility itself is a tradeable asset class. When an asset's realized
volatility is at an extreme relative to its own history, there is a
structural supply/demand imbalance in options market-making:

1. When vol is cheap (20th percentile), market makers under-hedge,
   creating positive convexity for long vol positions.
2. When vol is expensive (80th percentile), over-hedging by dealers
   creates negative convexity for long vol positions.
3. The vol mean-reversion trade (selling expensive vol, buying cheap vol)
   earns the vol risk premium over a 5-day horizon.

This is a *relative value* strategy: go long when vol is cheap (expect
realized vol to increase, benefiting from delta-gamma exposure) and
short when vol is expensive (expect mean-reversion down).

This is intentionally different from BVC (trial #1007) which trades
vol *continuation* on BTC. CVR trades vol *mean-reversion* on a
single asset's own history.

PRE-REGISTERED PARAMETERS (FROZEN — cannot be tuned after results)
================================================================
- vol_window    = 20        (realized vol lookback)
- rank_window   = 60        (percentile rank lookback)
- entry_low     = 20        (buy vol below this percentile)
- entry_high    = 80        (sell vol above this percentile)
- hold_days     = 5         (time exit)
- atr_period    = 14        (ATR window for stop sizing)
- stop_atr      = 2.0       (stop-loss in ATR multiples)

USAGE
=====
    from strategies.cross_asset_vol_rank import CVRConfig, compute_cvr_signals

    config = CVRConfig()                          # frozen defaults
    out = compute_cvr_signals(
        close=close_series,
        highs=high_series,
        lows=low_series,
        config=config,
    )
    # out.signal          : -1 / 0 / +1 single-bar entry
    # out.vol_percentile  : percentile rank of current vol (0-100)
    # out.config          : frozen CVRConfig
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Frozen configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CVRConfig:
    """Pre-registered configuration — frozen at module import time.

    Values match trial #1008 spec exactly:
        vol_window=20, rank_window=60, entry_low=20, entry_high=80,
        hold_days=5, atr_period=14, stop_atr=2.0.
    """

    vol_window: int = 20
    rank_window: int = 60
    entry_low: float = 20.0
    entry_high: float = 80.0
    hold_days: int = 5
    atr_period: int = 14
    stop_atr: float = 2.0


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


class CVRResult(NamedTuple):
    """Output of compute_cvr_signals()."""

    signal: pd.Series
    vol_percentile: pd.Series
    config: CVRConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _realized_vol(close: pd.Series, window: int) -> pd.Series:
    """Annualized realized volatility from log returns.

    Uses simple rolling std of log returns.
    """
    log_ret = np.log(close / close.shift(1))
    return log_ret.rolling(window=window, min_periods=window).std(ddof=1) * np.sqrt(252)


# ---------------------------------------------------------------------------
# Core signal computation
# ---------------------------------------------------------------------------


def compute_cvr_signals(
    close: pd.Series,
    highs: pd.Series,
    lows: pd.Series,
    config: CVRConfig | None = None,
) -> CVRResult:
    """Compute Cross-Asset Volatility Rank signals.

    Mechanism
    ---------
    1. Compute 20-day realized volatility from log returns.
    2. Rank current vol within a rolling 60-day window (percentile).
    3. Entry:
         - vol_percentile < entry_low  (20)  ->  LONG  (cheap vol, buy)
         - vol_percentile > entry_high (80)  ->  SHORT (expensive vol, sell)
    4. Single-bar entry signal. The validation pipeline / caller applies
       its own hold / exit logic.

    Parameters
    ----------
    close  : pd.Series of close prices (DatetimeIndex).
    highs  : pd.Series of high prices.
    lows   : pd.Series of low prices.
    config : frozen CVRConfig; defaults to pre-registered values.

    Returns
    -------
    CVRResult with signal, vol_percentile, config.
    """
    if config is None:
        config = CVRConfig()

    # Align on common index
    df = pd.concat(
        {"close": close, "high": highs, "low": lows},
        axis=1,
        join="inner",
    ).dropna()

    min_bars = max(config.vol_window + config.rank_window, config.atr_period) + 10
    if len(df) < min_bars:
        empty = pd.Series(0, index=df.index, dtype=int, name="signal")
        return CVRResult(
            signal=empty,
            vol_percentile=pd.Series(np.nan, index=df.index),
            config=config,
        )

    # 1) Realized vol (data through t-1 via shift)
    rv = _realized_vol(df["close"], config.vol_window).shift(1)

    # 2) Percentile rank within rolling window
    vol_pct = rv.rolling(
        window=config.rank_window, min_periods=config.rank_window
    ).rank(pct=True) * 100
    vol_pct.name = "vol_percentile"

    # 3) Entry: cheap vol -> long, expensive vol -> short
    signal = pd.Series(0, index=df.index, dtype=int, name="signal")
    signal[vol_pct < config.entry_low] = 1    # cheap vol -> long
    signal[vol_pct > config.entry_high] = -1  # expensive vol -> short

    return CVRResult(
        signal=signal,
        vol_percentile=vol_pct,
        config=config,
    )


__all__ = [
    "CVRConfig",
    "CVRResult",
    "compute_cvr_signals",
]

"""
Gold/Silver Spread (GSS) — ratio mean-reversion.

Trial #1006 in the quant_os edge-search ledger.

ECONOMIC RATIONALE
==================
The gold/silver ratio (XAUUSD / XAGUSD) is a structural relative-value
metric driven by differing industrial vs monetary demand for the two
metals. When the ratio deviates excessively from its rolling mean, the
spread is over- or under-priced relative to the equilibrium. Mean-reversion
occurs because:

1. Central bank and ETF rebalancing flows act as a restoring force.
2. Silver's industrial demand component creates mean-reverting mispricing
   relative to gold's monetary premium.
3. The 60-day window captures the medium-term equilibrium; extremes
   beyond 2 standard deviations represent dislocations that revert as
   the flow pressure subsides.

This is a *contrarian* strategy: when the ratio is elevated (gold expensive
relative to silver), we short the ratio (short XAU, long XAG); when the
ratio is depressed, we go long the ratio.

PRE-REGISTERED PARAMETERS (FROZEN — cannot be tuned after results)
================================================================
- ratio_window  = 60        (rolling mean/std window for the ratio)
- entry_z       = 2.0       (z-score threshold for entry)
- hold_days     = 10        (time exit if stop not hit)
- atr_period    = 14        (ATR window for stop sizing)
- stop_atr      = 1.5       (stop-loss in ATR multiples)

USAGE
=====
    from strategies.gold_silver_spread import GSSConfig, compute_gss_signals

    config = GSSConfig()                          # frozen defaults
    out = compute_gss_signals(
        xau_close=xau_close,
        xau_high=xau_high,
        xau_low=xau_low,
        xag_close=xag_close,
        config=config,
    )
    # out.signal    : -1 / 0 / +1 single-bar entry
    # out.ratio     : XAUUSD / XAGUSD
    # out.ratio_z   : z-score of ratio vs 60-day rolling mean
    # out.config    : frozen GSSConfig
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
class GSSConfig:
    """Pre-registered configuration — frozen at module import time.

    Values match trial #1006 spec exactly:
        ratio_window=60, entry_z=2.0, hold_days=10, atr_period=14,
        stop_atr=1.5.
    """

    ratio_window: int = 60
    entry_z: float = 2.0
    hold_days: int = 10
    atr_period: int = 14
    stop_atr: float = 1.5


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


class GSSResult(NamedTuple):
    """Output of compute_gss_signals()."""

    signal: pd.Series
    ratio: pd.Series
    ratio_z: pd.Series
    config: GSSConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int
) -> pd.Series:
    """Standard ATR — simple rolling mean (not Wilder-smoothed).

    Uses data through t-1 only via shift(1) at the call site.
    """
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()


# ---------------------------------------------------------------------------
# Core signal computation
# ---------------------------------------------------------------------------


def compute_gss_signals(
    xau_close: pd.Series,
    xau_high: pd.Series,
    xau_low: pd.Series,
    xag_close: pd.Series,
    config: GSSConfig | None = None,
) -> GSSResult:
    """Compute Gold/Silver Spread ratio mean-reversion signals.

    Mechanism
    ---------
    1. Compute ratio = XAUUSD / XAGUSD.
    2. Rolling 60-day mean and std of the ratio (data through t-1).
    3. Z-score: (ratio - rolling_mean) / rolling_std.
    4. Entry (contrarian):
         - z > +entry_z  ->  SHORT ratio (short gold, long silver)
         - z < -entry_z  ->  LONG  ratio (long gold, short silver)
    5. Single-bar entry signal. The validation pipeline / caller applies
       its own hold / exit logic.

    Parameters
    ----------
    xau_close : pd.Series of XAUUSD close prices (DatetimeIndex).
    xau_high  : pd.Series of XAUUSD high prices.
    xau_low   : pd.Series of XAUUSD low prices.
    xag_close : pd.Series of XAGUSD close prices.
    config    : frozen GSSConfig; defaults to pre-registered values.

    Returns
    -------
    GSSResult with signal, ratio, ratio_z, config.
    """
    if config is None:
        config = GSSConfig()

    # Align on common index (no forward fill — would leak)
    df = pd.concat(
        {
            "xau_close": xau_close,
            "xau_high": xau_high,
            "xau_low": xau_low,
            "xag_close": xag_close,
        },
        axis=1,
        join="inner",
    ).dropna()

    min_bars = max(config.ratio_window, config.atr_period) + 5
    if len(df) < min_bars:
        empty = pd.Series(0, index=df.index, dtype=int, name="signal")
        return GSSResult(
            signal=empty,
            ratio=pd.Series(np.nan, index=df.index),
            ratio_z=pd.Series(np.nan, index=df.index),
            config=config,
        )

    # 1) Ratio
    ratio = df["xau_close"] / df["xag_close"]
    ratio.name = "ratio"

    # 2) Rolling mean and std of ratio (data through t-1)
    ratio_mean = (
        ratio.rolling(window=config.ratio_window, min_periods=config.ratio_window)
        .mean()
        .shift(1)
    )
    ratio_std = (
        ratio.rolling(window=config.ratio_window, min_periods=config.ratio_window)
        .std(ddof=1)
        .shift(1)
    )

    # 3) Z-score
    ratio_z = (ratio - ratio_mean) / ratio_std.replace(0.0, np.nan)
    ratio_z.name = "ratio_z"

    # 4) Contrarian entry
    signal = pd.Series(0, index=df.index, dtype=int, name="signal")
    signal[ratio_z > config.entry_z] = -1   # ratio high -> short gold, long silver
    signal[ratio_z < -config.entry_z] = 1   # ratio low  -> long gold, short silver

    return GSSResult(
        signal=signal,
        ratio=ratio,
        ratio_z=ratio_z,
        config=config,
    )


__all__ = [
    "GSSConfig",
    "GSSResult",
    "compute_gss_signals",
]

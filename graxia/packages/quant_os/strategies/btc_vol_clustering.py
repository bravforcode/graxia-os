"""
BTC Volatility Clustering (BVC) — vol-continuation signal.

Trial #1007 in the quant_os edge-search ledger.

ECONOMIC RATIONALE
==================
Cryptocurrency volatility clusters differently than FX. In FX, vol
spikes are typically mean-reverting (a shock subsides). In crypto,
particularly BTCUSD, vol spikes tend to *persist* for 2-5 days because:

1. Leverage liquidation cascades create self-reinforcing vol.
2. Miner/whale rebalancing flows are multi-day, not single-bar.
3. 24/7 trading means the vol cycle doesn't pause for market close,
   allowing momentum to compound.

When 20-day realized vol spikes above 1.5x its own rolling mean, the
hypothesis is that the next day tends to continue in the same direction
as the vol expansion. This is a *vol-continuation* trade: long in the
direction of the vol expansion (upward move + vol spike = long; downward
move + vol spike = short).

This is intentionally a different mechanism from MRM (trial #1005)
which classifies macro regimes on real yields. BVC is a pure vol-
regime signal on BTCUSD itself.

PRE-REGISTERED PARAMETERS (FROZEN — cannot be tuned after results)
================================================================
- vol_window    = 20        (realized vol lookback)
- vol_threshold = 1.5       (vol spike = realized > threshold * rolling_mean)
- hold_days     = 3         (time exit if stop not hit)
- atr_period    = 14        (ATR window for stop sizing)
- stop_atr      = 2.0       (stop-loss in ATR multiples)

USAGE
=====
    from strategies.btc_vol_clustering import BVCConfig, compute_bvc_signals

    config = BVCConfig()                          # frozen defaults
    out = compute_bvc_signals(
        close=btc_close,
        highs=btc_high,
        lows=btc_low,
        config=config,
    )
    # out.signal    : -1 / 0 / +1 single-bar entry
    # out.vol_ratio : realized_vol / rolling_mean_vol
    # out.vol_rank  : percentile rank of vol_ratio
    # out.config    : frozen BVCConfig
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
class BVCConfig:
    """Pre-registered configuration — frozen at module import time.

    Values match trial #1007 spec exactly:
        vol_window=20, vol_threshold=1.5, hold_days=3, atr_period=14,
        stop_atr=2.0.
    """

    vol_window: int = 20
    vol_threshold: float = 1.5
    hold_days: int = 3
    atr_period: int = 14
    stop_atr: float = 2.0


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


class BVCResult(NamedTuple):
    """Output of compute_bvc_signals()."""

    signal: pd.Series
    vol_ratio: pd.Series
    vol_rank: pd.Series
    config: BVCConfig


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


def _realized_vol(close: pd.Series, window: int) -> pd.Series:
    """Annualized realized volatility from log returns.

    Uses simple rolling std of log returns.
    """
    log_ret = np.log(close / close.shift(1))
    return log_ret.rolling(window=window, min_periods=window).std(ddof=1) * np.sqrt(252)


# ---------------------------------------------------------------------------
# Core signal computation
# ---------------------------------------------------------------------------


def compute_bvc_signals(
    close: pd.Series,
    highs: pd.Series,
    lows: pd.Series,
    config: BVCConfig | None = None,
) -> BVCResult:
    """Compute BTC Volatility Clustering signals.

    Mechanism
    ---------
    1. Compute 20-day realized volatility from log returns.
    2. Rolling mean of realized vol (longer window, e.g. 60-day).
    3. Vol ratio = realized_vol / mean_vol. When vol_ratio > 1.5, vol
       is spiking.
    4. Direction: sign of close-to-close return over the vol window.
    5. Entry:
         - vol_ratio > threshold AND return > 0  ->  LONG  (vol up)
         - vol_ratio > threshold AND return < 0  ->  SHORT (vol down)
    6. Single-bar entry signal.

    Parameters
    ----------
    close  : pd.Series of BTCUSD close prices (DatetimeIndex).
    highs  : pd.Series of high prices.
    lows   : pd.Series of low prices.
    config : frozen BVCConfig; defaults to pre-registered values.

    Returns
    -------
    BVCResult with signal, vol_ratio, vol_rank, config.
    """
    if config is None:
        config = BVCConfig()

    # Align on common index
    df = pd.concat(
        {"close": close, "high": highs, "low": lows},
        axis=1,
        join="inner",
    ).dropna()

    min_bars = max(config.vol_window * 3, config.atr_period) + 10
    if len(df) < min_bars:
        empty = pd.Series(0, index=df.index, dtype=int, name="signal")
        return BVCResult(
            signal=empty,
            vol_ratio=pd.Series(np.nan, index=df.index),
            vol_rank=pd.Series(np.nan, index=df.index),
            config=config,
        )

    # 1) Realized vol (data through t-1 via shift)
    rv = _realized_vol(df["close"], config.vol_window).shift(1)

    # 2) Rolling mean of realized vol (longer window, through t-1)
    rv_mean = rv.rolling(window=60, min_periods=30).mean()

    # 3) Vol ratio
    vol_ratio = rv / rv_mean.replace(0.0, np.nan)
    vol_ratio.name = "vol_ratio"

    # 4) Vol rank (percentile, through t-1)
    vol_rank = vol_ratio.rolling(window=120, min_periods=30).rank(pct=True) * 100
    vol_rank.name = "vol_rank"

    # 5) Direction: sign of close-to-close return over vol_window
    direction = np.sign(df["close"].pct_change(config.vol_window)).shift(1)

    # 6) Entry: vol spike + direction
    vol_spike = vol_ratio > config.vol_threshold
    signal = pd.Series(0, index=df.index, dtype=int, name="signal")
    signal[vol_spike & (direction > 0)] = 1    # vol up + rising -> long
    signal[vol_spike & (direction < 0)] = -1   # vol up + falling -> short

    return BVCResult(
        signal=signal,
        vol_ratio=vol_ratio,
        vol_rank=vol_rank,
        config=config,
    )


__all__ = [
    "BVCConfig",
    "BVCResult",
    "compute_bvc_signals",
]

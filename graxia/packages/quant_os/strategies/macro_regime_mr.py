"""
Macro Regime Mean-Reversion (MRM) — regime-conditional signal.

Trial #1005 in the quant_os edge-search ledger (cumulative post-RYDC).

ECONOMIC RATIONALE
==================
Real (inflation-adjusted) yields are the structural driver of all
risk-asset valuations. When DFII10 is *stable* (low regime stdev),
the macro backdrop is quiet and price action mean-reverts within
the recent range — classical range-trading works. When DFII10 is
*trending* (high regime stdev relative to its own mean), macro
narratives are shifting, the cross-asset hedging flow is active,
and the same "mean-reversion" trade gets run over by a regime
break.

The candidate edge here is therefore NOT a pure mean-reversion
strategy and NOT a pure trend strategy. It is *regime-conditional
selection*:

    regime_window=30
    IF std(DFII10, 30d) / |mean(DFII10, 30d)|  <  regime_threshold:
        → mean reversion  (price > 2*ATR above rolling mean → short, etc.)
    ELSE:
        → momentum       (price > 2*ATR above rolling mean → long, etc.)

The same deviation threshold (2.0*ATR) flips its direction based on
the regime. The hypothesis is that regime-conditional switching
preserves the edge in both environments and avoids the largest
drawdowns that kill single-mode strategies.

This is intentionally a different mechanism from RYDC (trial #1001,
rejected on 2026-07-12) — RYDC tested cross-asset lead-lag on
contemporaneous residuals; this tests regime classification on real
yields first and then picks the trade direction *conditional* on
that regime. They are independent tests and the stopping rule
(stopping_rule_2026_07_12.md §3.1) counts this as a new trial.

PRE-REGISTERED PARAMETERS (FROZEN — cannot be tuned after results)
=================================================================
- regime_window  = 30        (DFII10 rolling window for regime classifier)
- mr_threshold   = 2.0*ATR   (entry distance from rolling mean, in ATR units)
- regime_threshold = 0.20    (std/mean of DFII10; classifies "stable" vs "trending")
- atr_period     = 14        (ATR window)
- mean_window    = 20        (rolling mean of close for entry reference)

USAGE
=====
    from strategies.macro_regime_mr import MRMConfig, compute_mrm_signals

    config = MRMConfig()                          # frozen defaults
    out = compute_mrm_signals(
        close=xau_close,
        highs=xau_high,
        lows=xau_low,
        dfii10=dfii10_yield_series,
        config=config,
    )
    # out["signal"]        : -1 / 0 / +1 single-bar entry
    # out["regime"]        : "stable" or "trending"
    # out["regime_score"]  : std(DFII10, 30d) / |mean(DFII10, 30d)|
    # out["deviation_atr"] : (close - mean_20) / ATR
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Regime classification
# ---------------------------------------------------------------------------


class Regime(str, Enum):
    """Macro regime classifier on the real-yield series."""

    STABLE = "stable"        # low CV of DFII10 → mean reversion
    TRENDING = "trending"    # high CV of DFII10 → momentum


# ---------------------------------------------------------------------------
# Frozen configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MRMConfig:
    """Pre-registered configuration — frozen at module import time.

    Values match trial #1005 spec exactly:
        regime_window=30, mr_threshold=2.0 (ATR units), atr_period=14,
        mean_window=20, regime_threshold=0.20.
    """

    regime_window: int = 30
    mr_threshold_atr: float = 2.0
    atr_period: int = 14
    mean_window: int = 20
    regime_threshold: float = 0.20  # std/|mean| of DFII10 separates regimes


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


class MRMResult(NamedTuple):
    """Output of compute_mrm_signals()."""

    signal: pd.Series
    regime: pd.Series
    regime_score: pd.Series
    atr: pd.Series
    rolling_mean: pd.Series
    deviation_atr: pd.Series
    config: MRMConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    """Standard ATR — simple rolling mean (not Wilder-smoothed) so the
    output is comparable across calls; the smoothing choice is part of
    the pre-registered spec.
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


def _regime_score(dfii10: pd.Series, window: int) -> pd.Series:
    """Coefficient of variation of DFII10 over `window` days.

    regime_score = std(DFII10, w) / |mean(DFII10, w)|

    Uses data through t-1 only (no look-ahead). Returns NaN during the
    warmup period.
    """
    mu = dfii10.rolling(window=window, min_periods=window).mean().shift(1)
    sd = dfii10.rolling(window=window, min_periods=window).std(ddof=1).shift(1)
    return sd / mu.abs().replace(0.0, np.nan)


# ---------------------------------------------------------------------------
# Core signal computation
# ---------------------------------------------------------------------------


def compute_mrm_signals(
    close: pd.Series,
    highs: pd.Series,
    lows: pd.Series,
    dfii10: pd.Series,
    config: MRMConfig | None = None,
) -> MRMResult:
    """Compute Macro-Regime Mean-Reversion signals for XAUUSD.

    Mechanism
    ---------
    1. Compute regime_score = std(DFII10, 30d) / |mean(DFII10, 30d)|
       (data through t-1). If regime_score < regime_threshold → STABLE
       (mean reversion), else → TRENDING (momentum).
    2. ATR(14) on the price series; rolling 20-bar mean of close.
    3. Deviation in ATR units: (close - rolling_mean_20) / ATR.
    4. Entry:
        - STABLE  AND deviation > +mr_threshold_atr → SHORT  (revert down)
        - STABLE  AND deviation < -mr_threshold_atr → LONG   (revert up)
        - TRENDING AND deviation > +mr_threshold_atr → LONG   (trend up)
        - TRENDING AND deviation < -mr_threshold_atr → SHORT  (trend down)
    5. Single-bar entry signal. The validation pipeline / caller applies
       its own hold / exit logic.

    Parameters
    ----------
    close   : pd.Series of XAUUSD close prices (DatetimeIndex).
    highs   : pd.Series of high prices.
    lows    : pd.Series of low prices.
    dfii10  : pd.Series of 10-year real (TIPS) yield, daily, in percent.
              Can be any scale; the regime_score is scale-invariant.
    config  : frozen MRMConfig; defaults to pre-registered values.

    Returns
    -------
    MRMResult with signal, regime, regime_score, atr, rolling_mean,
    deviation_atr.
    """
    if config is None:
        config = MRMConfig()

    # Align on common index (no forward fill — would leak)
    df = pd.concat(
        {"close": close, "high": highs, "low": lows, "dfii10": dfii10},
        axis=1,
        join="inner",
    ).dropna()

    if len(df) < max(config.regime_window, config.mean_window, config.atr_period) + 5:
        empty = pd.Series(0, index=df.index, dtype=int, name="signal")
        return MRMResult(
            signal=empty,
            regime=pd.Series("", index=df.index, dtype=object),
            regime_score=pd.Series(np.nan, index=df.index),
            atr=pd.Series(np.nan, index=df.index),
            rolling_mean=pd.Series(np.nan, index=df.index),
            deviation_atr=pd.Series(np.nan, index=df.index),
            config=config,
        )

    # 1) Regime
    score = _regime_score(df["dfii10"], config.regime_window)
    regime = pd.Series(Regime.TRENDING, index=df.index, dtype=object)
    regime[score < config.regime_threshold] = Regime.STABLE
    regime.name = "regime"
    score.name = "regime_score"

    # 2) ATR + rolling mean (data through t-1)
    atr = _atr(df["high"], df["low"], df["close"], config.atr_period).shift(1)
    rolling_mean = (
        df["close"]
        .rolling(window=config.mean_window, min_periods=config.mean_window)
        .mean()
        .shift(1)
    )

    # 3) Deviation in ATR units
    dev = (df["close"] - rolling_mean) / atr.replace(0.0, np.nan)
    dev.name = "deviation_atr"

    # 4) Regime-conditional entry
    is_stable = regime == Regime.STABLE
    is_trending = regime == Regime.TRENDING

    signal = pd.Series(0, index=df.index, dtype=int, name="signal")

    # STABLE → mean reversion (short the upper extreme, long the lower extreme)
    signal[is_stable & (dev > config.mr_threshold_atr)] = -1
    signal[is_stable & (dev < -config.mr_threshold_atr)] = 1

    # TRENDING → momentum (long the upper extreme, short the lower extreme)
    signal[is_trending & (dev > config.mr_threshold_atr)] = 1
    signal[is_trending & (dev < -config.mr_threshold_atr)] = -1

    atr.name = "atr"
    rolling_mean.name = "rolling_mean"

    return MRMResult(
        signal=signal,
        regime=regime,
        regime_score=score,
        atr=atr,
        rolling_mean=rolling_mean,
        deviation_atr=dev,
        config=config,
    )


__all__ = [
    "Regime",
    "MRMConfig",
    "MRMResult",
    "compute_mrm_signals",
]

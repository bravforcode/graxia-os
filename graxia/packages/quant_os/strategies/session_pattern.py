"""
Session Pattern (SP) — Volatility clustering by FX session.

Trial #1004 in the quant_os edge-search ledger (cumulative post-RYDC).

ECONOMIC RATIONALE
==================
FX markets are not uniform across the 24-hour day. Liquidity, the
*type* of participants, and average range differ systematically by
session:

    Asian session (00:00 - 07:00 UTC)  : low vol, range-bound, mean
                                         reversion dominates
    London session (07:00 - 12:00 UTC) : trending breakouts, momentum
    New York session (12:00 - 21:00 UTC): high vol, momentum at the
                                         London/NY overlap, reversal
                                         in the late NY session
    Late NY (21:00 - 24:00 UTC)        : thin book, fade extremes

The candidate edge here is *volatility-regime-conditional behavior*:
the same price-action pattern (e.g. 1.5x ATR outside a 20-bar mean)
is profitable in one session and unprofitable in another. Pre-registered
arms:

    - Low-vol session (Asian): mean reversion, enter when price
      deviates by `threshold` (0.5*ATR) from the session-relative
      mean, exit at the mean.
    - High-vol session (London / NY overlap): momentum, enter on
      directional break of the same threshold, trail the position
      for `session_window` bars.

PRE-REGISTERED PARAMETERS (FROZEN — cannot be tuned after results)
=================================================================
- session_window = 20      (rolling window for session-relative stats)
- threshold      = 0.5*ATR (entry distance from session mean in ATR units)
- atr_period     = 14      (ATR window)
- low_vol_session:  "asian"  (00:00-07:00 UTC)  → mean reversion
- high_vol_session: "london" (07:00-12:00 UTC)  → momentum
- high_vol_session: "ny"     (12:00-21:00 UTC)  → momentum

USAGE
=====
    from strategies.session_pattern import SPConfig, compute_sp_signals

    config = SPConfig()                       # frozen defaults
    out = compute_sp_signals(
        close=xau_h1_close,
        highs=xau_h1_high,
        lows=xau_h1_low,
        timestamps=idx,                        # DatetimeIndex
        config=config,
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Session definitions (UTC hours)
# ---------------------------------------------------------------------------


class Session(str, Enum):
    """FX session classifier. The hour ranges are pre-registered."""

    ASIAN = "asian"      # 00:00 - 07:00 UTC
    LONDON = "london"    # 07:00 - 12:00 UTC
    NEW_YORK = "ny"      # 12:00 - 21:00 UTC
    LATE_NY = "late_ny"  # 21:00 - 24:00 UTC (no-trade zone)


# ---------------------------------------------------------------------------
# Frozen configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SPConfig:
    """Pre-registered configuration — frozen at module import time.

    Values match trial #1004 spec exactly:
        session_window=20, threshold=0.5 (in ATR units).
    """

    session_window: int = 20
    threshold_atr: float = 0.5  # entry distance from session-relative mean, in ATR units
    atr_period: int = 14


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


class SPResult(NamedTuple):
    """Output of compute_sp_signals()."""

    signal: pd.Series            # -1 / 0 / +1 entries (single-bar, caller applies logic)
    session: pd.Series           # Session label per bar
    atr: pd.Series               # ATR(14) per bar
    session_mean: pd.Series      # rolling 20-bar session-aware mean of close
    deviation_atr: pd.Series     # (close - session_mean) / atr, in ATR units
    config: SPConfig


# ---------------------------------------------------------------------------
# Session classification
# ---------------------------------------------------------------------------


def _classify_session(index: pd.DatetimeIndex) -> pd.Series:
    """Classify each bar's timestamp into a Session label.

    All times are assumed to be in UTC. The caller is responsible for
    tz-conversion; we do NOT shift timezones here.
    """
    hour = pd.Series(index=index, data=index.hour)
    labels = pd.Series(Session.LATE_NY, index=index, dtype=object)
    labels[hour < 7] = Session.ASIAN
    labels[(hour >= 7) & (hour < 12)] = Session.LONDON
    labels[(hour >= 12) & (hour < 21)] = Session.NEW_YORK
    labels.name = "session"
    return labels


# ---------------------------------------------------------------------------
# Core signal computation
# ---------------------------------------------------------------------------


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    """Standard Average True Range. Uses a simple mean (not Wilder smooth)
    so the output is comparable across calls — the validation pipeline
    reads `atr` directly and the smoothing choice is part of the spec.
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


def compute_sp_signals(
    close: pd.Series,
    highs: pd.Series,
    lows: pd.Series,
    timestamps: pd.DatetimeIndex,
    config: SPConfig | None = None,
) -> SPResult:
    """Compute Session Pattern signals.

    Mechanism
    ---------
    1. Classify each bar into Asian / London / NY / Late-NY (UTC).
    2. Compute ATR(14) on the price series.
    3. Compute a rolling 20-bar mean of close *as the session-relative
       reference level*. We use a single 20-bar rolling mean (not
       per-session) to keep the lookback symmetric across the 24h
       boundary; the "session-relative" part comes from the
       classifier.
    4. Deviation in ATR units: (close - rolling_mean) / ATR.
    5. Entry:
        - ASIAN bar AND deviation < -threshold_atr  → LONG  (mean reversion)
        - ASIAN bar AND deviation > +threshold_atr  → SHORT (mean reversion)
        - LONDON or NY bar AND deviation > +threshold_atr → LONG  (momentum)
        - LONDON or NY bar AND deviation < -threshold_atr → SHORT (momentum)
        - LATE_NY bar → no signal (thin book).
    6. The signal series is single-bar; the validation pipeline / caller
       applies its own hold / exit logic (mean reversion typically exits
       at the session mean; momentum typically trails for
       `session_window` bars).

    Parameters
    ----------
    close      : pd.Series of close prices (DatetimeIndex, UTC).
    highs      : pd.Series of high prices.
    lows       : pd.Series of low prices.
    timestamps : the same DatetimeIndex as `close` (explicit for clarity
                 since we need `.hour` access).
    config     : frozen SPConfig; defaults to pre-registered values.

    Returns
    -------
    SPResult with signal, session, atr, session_mean, deviation_atr.
    """
    if config is None:
        config = SPConfig()

    # Align + drop NaN
    df = pd.concat(
        {"close": close, "high": highs, "low": lows},
        axis=1,
        join="inner",
    ).dropna()
    if len(df) < config.session_window + config.atr_period + 5:
        empty = pd.Series(0, index=df.index, dtype=int, name="signal")
        return SPResult(
            signal=empty,
            session=pd.Series("", index=df.index, dtype=object),
            atr=pd.Series(np.nan, index=df.index),
            session_mean=pd.Series(np.nan, index=df.index),
            deviation_atr=pd.Series(np.nan, index=df.index),
            config=config,
        )

    # Session classification
    session = _classify_session(df.index)

    # ATR + rolling mean (data through t-1 only)
    atr = _atr(df["high"], df["low"], df["close"], config.atr_period).shift(1)
    rolling_mean = df["close"].rolling(window=config.session_window, min_periods=config.session_window).mean().shift(1)

    # Deviation in ATR units
    dev = (df["close"] - rolling_mean) / atr.replace(0.0, np.nan)
    dev.name = "deviation_atr"

    # Build entry signal by session
    signal = pd.Series(0, index=df.index, dtype=int, name="signal")

    is_asian = session == Session.ASIAN
    is_london = session == Session.LONDON
    is_ny = session == Session.NEW_YORK
    is_momentum_session = is_london | is_ny

    # ASIAN: mean reversion
    signal[is_asian & (dev < -config.threshold_atr)] = 1   # long back to mean
    signal[is_asian & (dev > config.threshold_atr)] = -1   # short back to mean

    # LONDON / NY: momentum
    signal[is_momentum_session & (dev > config.threshold_atr)] = 1   # trend up
    signal[is_momentum_session & (dev < -config.threshold_atr)] = -1 # trend down

    # LATE_NY: no signal (already 0 by default)

    atr.name = "atr"
    rolling_mean.name = "session_mean"

    return SPResult(
        signal=signal,
        session=session,
        atr=atr,
        session_mean=rolling_mean,
        deviation_atr=dev,
        config=config,
    )


__all__ = [
    "Session",
    "SPConfig",
    "SPResult",
    "compute_sp_signals",
]

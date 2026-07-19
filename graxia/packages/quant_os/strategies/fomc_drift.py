"""
FOMC Drift â€” Post-FOMC directional drift for XAUUSD.

Trial #1010 in the quant_os edge-search ledger.

ECONOMIC RATIONALE
==================
FOMC decisions create asymmetric information events. Gold reacts to:
- Dovish surprises (rate cuts, dovish guidance) â†’ gold rallies
- Hawkish surprises (rate hikes, hawkish guidance) â†’ gold sells off

The "drift" is the tendency for gold to continue moving in the direction
of the initial reaction for 1-5 days after the announcement. This is
well-documented in equity markets (Bernanke & Kuttner 2005) and extends
to gold via real rate expectations.

Mechanism: Enter after FOMC close in the direction of the daily return
on the FOMC announcement day. Hold for a fixed drift window.

PRE-REGISTERED PARAMETERS (FROZEN)
===================================
- drift_window_days = 3      (days to hold after FOMC)
- min_fomc_return    = 0.002 (min |return| on FOMC day to trigger)
- max_fomc_return    = 0.03  (max |return| â€” reject outlier moves)
- atr_period         = 14    (ATR for stop sizing)
- stop_atr           = 2.0   (stop-loss in ATR multiples)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import NamedTuple

import numpy as np
import pandas as pd

from .event_filter import FOMC_DATES


# ---------------------------------------------------------------------------
# Frozen configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FOMCDriftConfig:
    """Pre-registered configuration for FOMC Drift strategy."""

    drift_window_days: int = 3
    min_fomc_return: float = 0.002
    max_fomc_return: float = 0.03
    atr_period: int = 14
    stop_atr: float = 2.0


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


class FOMCDriftResult(NamedTuple):
    """Output of compute_fomc_drift_signals()."""

    signal: pd.Series
    fomc_return: pd.Series
    drift_days_held: pd.Series
    config: FOMCDriftConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_fomc_dates() -> list[datetime]:
    """Parse FOMC_DATES into datetime objects (UTC)."""
    dates = []
    for ds in FOMC_DATES:
        try:
            dates.append(datetime.strptime(ds, "%Y-%m-%d").replace(tzinfo=UTC))
        except ValueError:
            continue
    return sorted(dates)


def _atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int
) -> pd.Series:
    """Standard ATR."""
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


def compute_fomc_drift_signals(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    config: FOMCDriftConfig | None = None,
) -> FOMCDriftResult:
    """Compute FOMC Drift signals for XAUUSD.

    Mechanism
    ---------
    1. Identify FOMC announcement days in the data.
    2. Compute the return on the FOMC day.
    3. If |return| is in [min_fomc_return, max_fomc_return]:
       - Enter in the direction of the FOMC return at next bar open.
       - Hold for drift_window_days bars.
    4. Exit after drift_window_days (time exit).

    Parameters
    ----------
    close : pd.Series of daily close prices (DatetimeIndex).
    high : pd.Series of daily highs.
    low : pd.Series of daily lows.
    config : frozen FOMCDriftConfig; defaults to pre-registered values.

    Returns
    -------
    FOMCDriftResult with signal, fomc_return, drift_days_held, config.
    """
    if config is None:
        config = FOMCDriftConfig()

    df = pd.DataFrame({"close": close, "high": high, "low": low}).dropna()

    if len(df) < config.atr_period + 10:
        empty = pd.Series(0, index=df.index, dtype=int, name="signal")
        return FOMCDriftResult(
            signal=empty,
            fomc_return=pd.Series(np.nan, index=df.index),
            drift_days_held=pd.Series(0, index=df.index),
            config=config,
        )

    # Ensure DatetimeIndex
    if not isinstance(df.index, pd.DatetimeIndex):
        try:
            df.index = pd.to_datetime(df.index)
        except Exception:
            empty = pd.Series(0, index=df.index, dtype=int, name="signal")
            return FOMCDriftResult(
                signal=empty,
                fomc_return=pd.Series(np.nan, index=df.index),
                drift_days_held=pd.Series(0, index=df.index),
                config=config,
            )

    # Parse FOMC dates
    fomc_dates = _parse_fomc_dates()

    # Compute daily returns
    daily_return = df["close"].pct_change()

    # Identify FOMC days in the data
    # FOMC dates are date-only; match to index dates
    fomc_date_set = {d.date() for d in fomc_dates}
    is_fomc = pd.Series(False, index=df.index)
    for i, idx in enumerate(df.index):
        try:
            if idx.date() in fomc_date_set:
                is_fomc.iloc[i] = True
        except Exception:
            continue

    # Signal generation
    signal = pd.Series(0, index=df.index, dtype=int, name="signal")
    fomc_ret = pd.Series(np.nan, index=df.index, name="fomc_return")
    days_held = pd.Series(0, index=df.index, name="drift_days_held")

    in_position = 0
    bars_remaining = 0

    for i in range(len(df)):
        if is_fomc.iloc[i]:
            ret = daily_return.iloc[i]
            if pd.isna(ret):
                continue
            fomc_ret.iloc[i] = ret

            # Check if return is in acceptable range
            if config.min_fomc_return <= abs(ret) <= config.max_fomc_return:
                # Enter in direction of FOMC return
                in_position = 1 if ret > 0 else -1
                bars_remaining = config.drift_window_days

        if in_position != 0:
            signal.iloc[i] = in_position
            days_held.iloc[i] = config.drift_window_days - bars_remaining + 1
            bars_remaining -= 1
            if bars_remaining <= 0:
                in_position = 0

    return FOMCDriftResult(
        signal=signal,
        fomc_return=fomc_ret,
        drift_days_held=days_held,
        config=config,
    )


__all__ = [
    "FOMCDriftConfig",
    "FOMCDriftResult",
    "compute_fomc_drift_signals",
]

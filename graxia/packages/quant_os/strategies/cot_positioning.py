"""
COT Positioning â€” CFTC Contrarian signal for XAUUSD.

Trial #1009 in the quant_os edge-search ledger.

ECONOMIC RATIONALE
==================
CFTC Disaggregated COT data captures actual futures positioning by
Managed Money (hedge funds, CTAs). When positioning reaches extremes,
it signals crowding â€” no marginal buyers (or sellers) left.

Contrarian logic:
- Extreme net-long â†’ short bias (no marginal buyers)
- Extreme net-short â†’ long bias (no marginal sellers)

This is a *fundamental positioning* signal, not a price-based signal.
Different data type, different frequency (weekly), different mechanism
(crowding vs price action) from all 11 rejected hypotheses.

PRE-REGISTERED PARAMETERS (FROZEN)
===================================
- lookback_weeks     = 52     (rolling window for z-score)
- entry_z            = 2.0    (z-score threshold for entry)
- exit_z             = 0.5    (z-score threshold for exit)
- min_hold_weeks     = 1      (minimum hold period)
- max_hold_weeks     = 4      (maximum hold period)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Frozen configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class COTPositioningConfig:
    """Pre-registered configuration for COT Positioning strategy."""

    lookback_weeks: int = 52
    entry_z: float = 2.0
    exit_z: float = 0.5
    min_hold_weeks: int = 1
    max_hold_weeks: int = 4


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


class COTPositioningResult(NamedTuple):
    """Output of compute_cot_positioning_signals()."""

    signal: pd.Series
    net_positioning: pd.Series
    zscore: pd.Series
    config: COTPositioningConfig


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_cot_data(data_dir: str | Path) -> pd.DataFrame:
    """Load and concatenate COT parquet files from a directory.

    Returns DataFrame with columns: date, net_positioning, long, short.
    """
    data_path = Path(data_dir)
    frames = []

    for f in sorted(data_path.glob("cot_*.parquet")):
        try:
            df = pd.read_parquet(f)
            frames.append(df)
        except Exception:
            continue

    if not frames:
        return pd.DataFrame(columns=["date", "net_positioning", "long", "short"])

    combined = pd.concat(frames, ignore_index=True)

    # Normalize column names
    col_map = {}
    for col in combined.columns:
        lower = col.lower().replace(" ", "_")
        if lower == "date":
            col_map[col] = "date"
        elif "positions_long_all" in lower and "m_money" in lower:
            col_map[col] = "long"
        elif "positions_short_all" in lower and "m_money" in lower:
            col_map[col] = "short"
        elif "managed" in lower and "long" in lower:
            col_map[col] = "long"
        elif "managed" in lower and "short" in lower:
            col_map[col] = "short"
        elif "net" in lower and "position" in lower:
            col_map[col] = "net_positioning"

    if col_map:
        combined = combined.rename(columns=col_map)

    # Compute net positioning if not present
    if "net_positioning" not in combined.columns and "long" in combined.columns and "short" in combined.columns:
        combined["net_positioning"] = combined["long"] - combined["short"]

    if "date" in combined.columns:
        combined["date"] = pd.to_datetime(combined["date"], errors="coerce")
        combined = combined.dropna(subset=["date"])
        combined = combined.sort_values("date").reset_index(drop=True)

    return combined


# ---------------------------------------------------------------------------
# Core signal computation
# ---------------------------------------------------------------------------


def compute_cot_positioning_signals(
    dates: pd.DatetimeIndex | pd.Series,
    net_positioning: pd.Series,
    config: COTPositioningConfig | None = None,
) -> COTPositioningResult:
    """Compute COT Positioning contrarian signals.

    Mechanism
    ---------
    1. Compute z-score of net positioning vs lookback-weeks rolling window.
    2. Entry (contrarian):
         - z > +entry_z  â†’  SHORT (extreme net-long = crowding)
         - z < -entry_z  â†’  LONG  (extreme net-short = crowding)
    3. Exit when z reverts to Â±exit_z.
    4. Maximum hold period: max_hold_weeks.

    Parameters
    ----------
    dates : DatetimeIndex or Series of dates (weekly frequency).
    net_positioning : Series of net positioning values (Long - Short).
    config : frozen COTPositioningConfig; defaults to pre-registered values.

    Returns
    -------
    COTPositioningResult with signal, net_positioning, zscore, config.
    """
    if config is None:
        config = COTPositioningConfig()

    # Build DataFrame
    df = pd.DataFrame({
        "date": pd.to_datetime(dates),
        "net_positioning": net_positioning.values if hasattr(net_positioning, 'values') else net_positioning,
    }).dropna().sort_values("date").reset_index(drop=True)

    if len(df) < config.lookback_weeks + 5:
        empty = pd.Series(0, index=df.index, dtype=int, name="signal")
        return COTPositioningResult(
            signal=empty,
            net_positioning=df["net_positioning"],
            zscore=pd.Series(np.nan, index=df.index),
            config=config,
        )

    # 1) Z-score (data through t-1 to avoid look-ahead)
    np_series = df["net_positioning"]
    rolling_mean = np_series.rolling(window=config.lookback_weeks, min_periods=config.lookback_weeks).mean().shift(1)
    rolling_std = np_series.rolling(window=config.lookback_weeks, min_periods=config.lookback_weeks).std(ddof=1).shift(1)
    zscore = (np_series - rolling_mean) / rolling_std.replace(0.0, np.nan)
    zscore.name = "zscore"

    # 2) Signal generation
    signal = pd.Series(0, index=df.index, dtype=int, name="signal")
    in_position = 0
    bars_in_position = 0

    for i in range(len(zscore)):
        z = zscore.iloc[i]
        if pd.isna(z):
            continue

        if in_position == 0:
            if z > config.entry_z:
                in_position = -1  # extreme long â†’ short
                bars_in_position = 0
            elif z < -config.entry_z:
                in_position = 1   # extreme short â†’ long
                bars_in_position = 0
        else:
            bars_in_position += 1
            # Exit conditions
            if in_position == -1 and z < config.exit_z:
                in_position = 0
            elif in_position == 1 and z > -config.exit_z:
                in_position = 0
            elif bars_in_position >= config.max_hold_weeks:
                in_position = 0  # time exit

        signal.iloc[i] = in_position

    return COTPositioningResult(
        signal=signal,
        net_positioning=np_series,
        zscore=zscore,
        config=config,
    )


__all__ = [
    "COTPositioningConfig",
    "COTPositioningResult",
    "load_cot_data",
    "compute_cot_positioning_signals",
]

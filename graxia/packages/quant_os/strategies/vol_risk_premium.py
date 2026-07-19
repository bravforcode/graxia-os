"""
Vol Risk Premium â€” Harvesting the implied-realized vol spread for XAUUSD.

Trial #1014 in the quant_os edge-search ledger.

ECONOMIC RATIONALE
==================
Options implied volatility (GVZ for gold) tends to exceed realized
volatility â€” the "volatility risk premium" (VRP). This premium exists
because options buyers overpay for tail-risk protection.

Strategy:
- When VRP is high (implied >> realized) â†’ sell vol (short gold vol,
  or equivalently, mean-revert expecting vol to drop)
- When VRP is negative (realized >> implied) â†’ buy vol (expect vol
  to stay elevated, trend-following)

In practice, we trade the *directional* implication:
- High VRP â†’ gold likely to stay range-bound â†’ mean-reversion signal
- Negative VRP â†’ gold in vol expansion â†’ trend-following signal

PRE-REGISTERED PARAMETERS (FROZEN)
===================================
- vrp_lookback       = 20    (rolling VRP z-score window)
- entry_z            = 1.5   (z-score for regime switch)
- exit_z             = 0.5   (z-score for exit)
- realized_vol_window = 20   (realized vol computation)
- gvz_smoothing      = 5     (GVZ smoothing window)
- regime_threshold   = 0.0   (VRP > 0 = premium regime)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd

from ..core.volatility_features import compute_realized_vol


# ---------------------------------------------------------------------------
# Frozen configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VolRiskPremiumConfig:
    """Pre-registered configuration for Vol Risk Premium strategy."""

    vrp_lookback: int = 20
    entry_z: float = 1.5
    exit_z: float = 0.5
    realized_vol_window: int = 20
    gvz_smoothing: int = 5
    regime_threshold: float = 0.0


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


class VolRiskPremiumResult(NamedTuple):
    """Output of compute_vol_risk_premium_signals()."""

    signal: pd.Series
    vrp: pd.Series
    vrp_zscore: pd.Series
    implied_vol: pd.Series
    realized_vol: pd.Series
    config: VolRiskPremiumConfig


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_gvz_data(data_dir: str | Path) -> pd.Series:
    """Load GVZ (Gold VIX) data from parquet files.

    Returns Series with DatetimeIndex and GVZ values.
    """
    data_path = Path(data_dir)
    frames = []

    for f in sorted(data_path.glob("*GVZ*.parquet")):
        try:
            df = pd.read_parquet(f)
            frames.append(df)
        except Exception:
            continue

    if not frames:
        return pd.Series(dtype=float, name="gvz")

    combined = pd.concat(frames)

    # Normalize column names
    col_map = {}
    for col in combined.columns:
        lower = col.lower()
        if "gvz" in lower or "close" in lower or "value" in lower:
            col_map[col] = "gvz"
        elif "date" in lower:
            col_map[col] = "date"

    if col_map:
        combined = combined.rename(columns=col_map)

    if "date" in combined.columns:
        combined["date"] = pd.to_datetime(combined["date"], errors="coerce")
        combined = combined.dropna(subset=["date"])
        combined = combined.set_index("date").sort_index()

    if "gvz" in combined.columns:
        return combined["gvz"].dropna()

    # If single column, use it
    if len(combined.columns) == 1:
        return combined.iloc[:, 0].dropna()

    return pd.Series(dtype=float, name="gvz")


# ---------------------------------------------------------------------------
# Core signal computation
# ---------------------------------------------------------------------------


def compute_vol_risk_premium_signals(
    close: pd.Series,
    implied_vol: pd.Series | None = None,
    config: VolRiskPremiumConfig | None = None,
) -> VolRiskPremiumResult:
    """Compute Vol Risk Premium signals for XAUUSD.

    Mechanism
    ---------
    1. Compute realized volatility (annualized).
    2. Load or use provided implied volatility (GVZ).
    3. VRP = implied_vol - realized_vol.
    4. Compute z-score of VRP over lookback window.
    5. Regime detection:
         - VRP z > entry_z  â†’  HIGH premium regime (mean-reversion)
         - VRP z < -entry_z â†’  LOW premium / vol expansion (trend-following)
    6. Signal:
         - HIGH premium (VRP z > entry_z): expect vol contraction â†’ LONG
           (mean-reversion: buy dips, sell rips)
         - LOW premium (VRP z < -entry_z): expect vol expansion â†’ follow
           recent direction (trend)
         - Neutral: no signal

    Parameters
    ----------
    close : pd.Series of daily close prices (DatetimeIndex).
    implied_vol : pd.Series of implied vol (GVZ). If None, uses
                  realized vol as proxy (degraded mode).
    config : frozen VolRiskPremiumConfig; defaults to pre-registered values.

    Returns
    -------
    VolRiskPremiumResult with signal, vrp, vrp_zscore, implied_vol,
    realized_vol, config.
    """
    if config is None:
        config = VolRiskPremiumConfig()

    df = pd.DataFrame({"close": close}).dropna()

    if len(df) < config.vrp_lookback + config.realized_vol_window + 10:
        empty = pd.Series(0, index=df.index, dtype=int, name="signal")
        nan_s = pd.Series(np.nan, index=df.index)
        return VolRiskPremiumResult(
            signal=empty,
            vrp=nan_s,
            vrp_zscore=nan_s,
            implied_vol=nan_s,
            realized_vol=nan_s,
            config=config,
        )

    # 1) Realized vol
    rv = compute_realized_vol(df["close"], config.realized_vol_window)

    # 2) Implied vol
    if implied_vol is not None and not implied_vol.empty:
        # Align implied vol to close index
        iv_index = implied_vol.index
        df_index = df.index
        # Normalize timezones for alignment
        if hasattr(iv_index, 'tz') and iv_index.tz is not None and hasattr(df_index, 'tz') and df_index.tz is None:
            iv_index = iv_index.tz_localize(None)
            implied_vol = implied_vol.copy()
            implied_vol.index = iv_index
            df_index = df_index.tz_localize(None)
            df_temp = df.copy()
            df_temp.index = df_index
        elif hasattr(df_index, 'tz') and df_index.tz is not None and hasattr(iv_index, 'tz') and iv_index.tz is None:
            df_index = df_index.tz_localize(None)
            df_temp = df.copy()
            df_temp.index = df_index
        else:
            df_temp = df

        iv = implied_vol.reindex(df_temp.index).ffill().bfill()
        # Smooth GVZ
        iv = iv.rolling(window=config.gvz_smoothing, min_periods=1).mean()
        iv.index = df.index  # Restore original index
    else:
        # Degraded mode: use realized vol as proxy (VRP = 0)
        iv = rv.copy()

    # 3) VRP = implied - realized
    vrp = iv - rv
    vrp.name = "vrp"

    # 4) VRP z-score
    vrp_mean = vrp.rolling(window=config.vrp_lookback, min_periods=config.vrp_lookback).mean().shift(1)
    vrp_std = vrp.rolling(window=config.vrp_lookback, min_periods=config.vrp_lookback).std(ddof=1).shift(1)
    vrp_z = (vrp - vrp_mean) / vrp_std.replace(0, np.nan)
    vrp_z.name = "vrp_zscore"

    # 5) Signal generation
    signal = pd.Series(0, index=df.index, dtype=int, name="signal")
    returns = df["close"].pct_change()
    in_position = 0

    for i in range(len(df)):
        z = vrp_z.iloc[i]
        if pd.isna(z):
            continue

        if in_position == 0:
            if z > config.entry_z:
                # High VRP â†’ mean-reversion regime â†’ long (expect vol contraction)
                in_position = 1
            elif z < -config.entry_z:
                # Low VRP â†’ vol expansion â†’ follow recent direction
                recent_ret = returns.iloc[max(0, i - 5):i].sum()
                in_position = 1 if recent_ret > 0 else -1
        elif in_position == 1:
            if z < config.exit_z and z > -config.exit_z:
                in_position = 0
        elif in_position == -1:
            if z > -config.exit_z:
                in_position = 0

        signal.iloc[i] = in_position

    return VolRiskPremiumResult(
        signal=signal,
        vrp=vrp,
        vrp_zscore=vrp_z,
        implied_vol=iv,
        realized_vol=rv,
        config=config,
    )


__all__ = [
    "VolRiskPremiumConfig",
    "VolRiskPremiumResult",
    "load_gvz_data",
    "compute_vol_risk_premium_signals",
]

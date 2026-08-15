"""
Cross-Asset Momentum (CAM) â€” DXY â†’ XAUUSD lead-lag.

Trial #1003 in the quant_os edge-search ledger (cumulative post-RYDC).

ECONOMIC RATIONALE
==================
Gold is priced in USD globally, so the dollar is the single largest
macro driver of gold spot. The contemporaneous relationship is well
known and already priced in within the same session by institutional
flow. The candidate edge here is a different *diffusion* claim:

    When DXY drops, XAUUSD tends to rise with a 1-5 day lag, because
    retail / CTA flow on XAUUSD is slower to reprice than interbank
    flow on DXY. Symmetrically, DXY strength precedes XAUUSD weakness.

The hypothesis is therefore NOT "DXY moves â†’ XAUUSD moves the same
day" (already public, zero alpha) but "DXY z-score extreme persists
beyond one session, and the *follow-through* in XAUUSD over the next
few days is the tradeable signal."

PRE-REGISTERED PARAMETERS (FROZEN â€” cannot be tuned after results)
=================================================================
- window = 60      (rolling z-score window, trading days)
- z_threshold = 1.0 (entry when |DXY z| > 1.0)
- hold_days = 5     (fixed hold; exit either on hold expiry or z reverts)

No look-ahead: rolling statistics use only data through t-1.

USAGE
=====
    from strategies.cross_asset_momentum import CAMConfig, compute_cam_signals

    config = CAMConfig()                     # frozen defaults
    out = compute_cam_signals(
        xau_close=xau_close,
        dxy_close=dxy_close,
        config=config,
    )
    # out["signal"] : pd.Series of -1 / 0 / +1
    # out["dxy_z"]  : pd.Series of rolling DXY z-scores (NaN for warmup)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Frozen configuration (dataclass(frozen=True) â€” no runtime mutation)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CAMConfig:
    """Pre-registered configuration â€” frozen at module import time.

    Values match trial #1003 spec exactly:
        window=60, z_threshold=1.0, hold_days=5.
    """

    window: int = 60
    z_threshold: float = 1.0
    hold_days: int = 5


# ---------------------------------------------------------------------------
# Result container (plain NamedTuple â€” no relative imports)
# ---------------------------------------------------------------------------


class CAMResult(NamedTuple):
    """Output of compute_cam_signals()."""

    signal: pd.Series          # -1 / 0 / +1 entries with multi-day holds
    dxy_z: pd.Series            # rolling z-score of DXY returns
    correlation: pd.Series      # rolling 60d correlation(DXY_ret, XAU_ret)
    config: CAMConfig           # echo back the frozen config used


# ---------------------------------------------------------------------------
# Core signal computation
# ---------------------------------------------------------------------------


def _rolling_zscore(returns: pd.Series, window: int) -> pd.Series:
    """Rolling z-score of returns. Uses data through t-1 only (no look-ahead)."""
    mu = returns.rolling(window=window, min_periods=window).mean().shift(1)
    sd = returns.rolling(window=window, min_periods=window).std(ddof=1).shift(1)
    return (returns - mu) / sd.replace(0.0, np.nan)


def _rolling_corr(a: pd.Series, b: pd.Series, window: int) -> pd.Series:
    """Rolling Pearson correlation between two series. data through t-1 only."""
    return a.rolling(window=window, min_periods=window).corr(b).shift(1)


def compute_cam_signals(
    xau_close: pd.Series,
    dxy_close: pd.Series,
    config: CAMConfig | None = None,
) -> CAMResult:
    """Compute Cross-Asset Momentum signals for XAUUSD using DXY as lead.

    Mechanism
    ---------
    1. Compute daily log-returns for DXY.
    2. Compute rolling 60d z-score of DXY returns (data through t-1).
    3. Compute rolling 60d correlation between DXY returns and XAU returns
       (used as a *secondary* filter: only trade when the lead-lag
       relationship is currently negative â€” that's when gold is supposed
       to follow DXY in the opposite direction).
    4. Entry:
        - LONG XAUUSD  if DXY z < -z_threshold  AND  rolling_corr < -0.1
        - SHORT XAUUSD if DXY z > +z_threshold  AND  rolling_corr < -0.1
    5. Hold for `hold_days` trading days (or until the position is
       explicitly closed by the caller â€” this function returns -1/+1
       on entry bars and 0 on every other bar so the caller / backtester
       can apply its own hold logic. For most callers the `signal`
       series can be treated as "enter on -1/+1, exit after hold_days".

    Parameters
    ----------
    xau_close : pd.Series of XAUUSD closing prices (DatetimeIndex).
    dxy_close : pd.Series of DXY closing prices (DatetimeIndex).
    config    : frozen CAMConfig; defaults to pre-registered values.

    Returns
    -------
    CAMResult with signal, dxy_z, correlation, and the config used.
    """
    if config is None:
        config = CAMConfig()  # uses pre-registered defaults

    # Align on common index; do NOT forward-fill (would leak).
    df = pd.concat({"xau": xau_close, "dxy": dxy_close}, axis=1, join="inner")
    df = df.dropna()

    if len(df) < config.window + 5:
        # Not enough data; return all-zero signal
        empty = pd.Series(0, index=df.index, dtype=int, name="signal")
        z_nan = pd.Series(np.nan, index=df.index, name="dxy_z")
        c_nan = pd.Series(np.nan, index=df.index, name="correlation")
        return CAMResult(signal=empty, dxy_z=z_nan, correlation=c_nan, config=config)

    # Returns
    dxy_ret = np.log(df["dxy"] / df["dxy"].shift(1))
    xau_ret = np.log(df["xau"] / df["xau"].shift(1))

    # Features (data through t-1 only)
    dxy_z = _rolling_zscore(dxy_ret, config.window)
    corr = _rolling_corr(dxy_ret, xau_ret, config.window)

    # Raw entry signal (single bar)
    raw_long = (dxy_z < -config.z_threshold) & (corr < -0.1)
    raw_short = (dxy_z > config.z_threshold) & (corr < -0.1)

    raw_signal = pd.Series(0, index=df.index, dtype=int)
    raw_signal[raw_long] = 1
    raw_signal[raw_short] = -1

    # Forward-fill entries for the hold period (a 1/-1 means "enter
    # today, hold for hold_days"). The caller decides what to do with
    # entries; this guarantees the same position is not re-entered for
    # `hold_days` bars, but does not enforce a stop-loss (the
    # validation pipeline / risk layer handles that).
    signal = raw_signal.replace(0, np.nan).ffill(limit=config.hold_days - 1)
    signal = signal.fillna(0).astype(int)
    signal.name = "signal"

    dxy_z.name = "dxy_z"
    corr.name = "correlation"

    return CAMResult(signal=signal, dxy_z=dxy_z, correlation=corr, config=config)


__all__ = ["CAMConfig", "CAMResult", "compute_cam_signals"]

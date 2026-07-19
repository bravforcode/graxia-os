"""
Vol Regime Sizing â€” Adaptive position sizing based on volatility regime.

Trial #1011 in the quant_os edge-search ledger.

ECONOMIC RATIONALE
==================
Volatility clusters â€” high-vol regimes persist and mean-revert. By sizing
positions inversely to expected volatility:
- Reduce size when vol is high (protect capital)
- Increase size when vol is low (capture trend with less noise)

This is NOT a directional signal â€” it's a position-sizing overlay that
improves risk-adjusted returns of any underlying signal.

Uses HAR (Heterogeneous Autoregressive) model for vol forecasting:
Corsi (2009): RV_t+1 = b0 + b1*RV_day + b2*RV_week + b3*RV_month

PRE-REGISTERED PARAMETERS (FROZEN)
===================================
- vol_target_annual  = 0.10  (target annualized volatility)
- vol_lookback       = 20    (realized vol window)
- regime_window      = 252   (regime percentile window)
- low_vol_pctile     = 0.33  (LOW regime threshold)
- high_vol_pctile    = 0.67  (HIGH regime threshold)
- size_low           = 1.5   (size multiplier in LOW vol)
- size_med           = 1.0   (size multiplier in MED vol)
- size_high          = 0.5   (size multiplier in HIGH vol)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

import numpy as np
import pandas as pd

from ..core.volatility_features import (
    compute_parkinson_vol,
    compute_realized_vol,
    compute_vol_regime,
)
from ..ml.har_model import HARModel


# ---------------------------------------------------------------------------
# Frozen configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VolRegimeSizingConfig:
    """Pre-registered configuration for Vol Regime Sizing."""

    vol_target_annual: float = 0.10
    vol_lookback: int = 20
    regime_window: int = 252
    low_vol_pctile: float = 0.33
    high_vol_pctile: float = 0.67
    size_low: float = 1.5
    size_med: float = 1.0
    size_high: float = 0.5


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


class VolRegimeSizingResult(NamedTuple):
    """Output of compute_vol_regime_sizing()."""

    size_multiplier: pd.Series
    realized_vol: pd.Series
    forecast_vol: pd.Series
    vol_regime: pd.Series
    config: VolRegimeSizingConfig


# ---------------------------------------------------------------------------
# Core signal computation
# ---------------------------------------------------------------------------


def compute_vol_regime_sizing(
    close: pd.Series,
    high: pd.Series | None = None,
    low: pd.Series | None = None,
    config: VolRegimeSizingConfig | None = None,
) -> VolRegimeSizingResult:
    """Compute vol-regime-based position size multiplier.

    Mechanism
    ---------
    1. Compute realized volatility (close-to-close, annualized).
    2. Classify regime: LOW / MED / HIGH based on rolling percentiles.
    3. Apply HAR model to forecast next-period vol (optional enhancement).
    4. Size multiplier:
         - LOW regime  â†’ size_low (1.5x) â€” more aggressive
         - MED regime  â†’ size_med (1.0x) â€” neutral
         - HIGH regime â†’ size_high (0.5x) â€” defensive

    Parameters
    ----------
    close : pd.Series of daily close prices.
    high : pd.Series of daily highs (optional, for Parkinson vol).
    low : pd.Series of daily lows (optional, for Parkinson vol).
    config : frozen VolRegimeSizingConfig; defaults to pre-registered values.

    Returns
    -------
    VolRegimeSizingResult with size_multiplier, realized_vol, forecast_vol,
    vol_regime, config.
    """
    if config is None:
        config = VolRegimeSizingConfig()

    df = pd.DataFrame({"close": close}).dropna()

    if len(df) < config.regime_window + 10:
        ones = pd.Series(config.size_med, index=df.index, name="size_multiplier")
        nan_s = pd.Series(np.nan, index=df.index)
        return VolRegimeSizingResult(
            size_multiplier=ones,
            realized_vol=nan_s,
            forecast_vol=nan_s,
            vol_regime=pd.Series("MED", index=df.index),
            config=config,
        )

    # 1) Realized vol
    rv = compute_realized_vol(df["close"], config.vol_lookback)

    # 2) Vol regime classification
    regime = compute_vol_regime(rv, config.regime_window)

    # 3) HAR forecast (optional â€” fit on available data)
    forecast_vol = pd.Series(np.nan, index=df.index, name="forecast_vol")
    try:
        har = HARModel()
        valid_rv = rv.dropna()
        if len(valid_rv) > 60:
            har.fit(valid_rv)
            # Walk-forward 1-step forecasts
            for i in range(60, len(valid_rv)):
                history = valid_rv.iloc[:i]
                pred = har.predict(history, steps=1)
                if len(pred) > 0:
                    idx = valid_rv.index[i]
                    if idx in forecast_vol.index:
                        forecast_vol.loc[idx] = pred.iloc[0]
    except Exception:
        pass  # HAR is optional enhancement

    # 4) Size multiplier based on regime
    size_mult = pd.Series(config.size_med, index=df.index, name="size_multiplier")

    for i in range(len(df)):
        r = regime.iloc[i] if i < len(regime) else "MED"
        if pd.isna(r):
            r = "MED"
        r_str = str(r)
        if r_str == "LOW":
            size_mult.iloc[i] = config.size_low
        elif r_str == "HIGH":
            size_mult.iloc[i] = config.size_high
        else:
            size_mult.iloc[i] = config.size_med

    return VolRegimeSizingResult(
        size_multiplier=size_mult,
        realized_vol=rv,
        forecast_vol=forecast_vol,
        vol_regime=regime,
        config=config,
    )


__all__ = [
    "VolRegimeSizingConfig",
    "VolRegimeSizingResult",
    "compute_vol_regime_sizing",
]

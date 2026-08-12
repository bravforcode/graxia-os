"""
Time-Series Momentum (TSMOM) signal.
Moskowitz, Ooi, Pedersen (2012): Trend-following across timeframes.
Multi-timeframe: 1M, 3M, 12M lookback.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class TSMOMSignal:
    """TSMOM signal result."""

    signal: pd.Series  # Signal: -1, 0, +1
    strength: pd.Series  # Signal strength: 0-1
    lookback_returns: dict  # Returns at each lookback
    consensus: pd.Series  # Multi-timeframe consensus


def compute_tsmom_signal(
    close: pd.Series,
    lookbacks: list[int] | None = None,
    vol_target: float = 0.10,
) -> TSMOMSignal:
    """
    Compute TSMOM signal across multiple lookbacks.

    Args:
        close: Price series
        lookbacks: List of lookback periods in bars (default: 1M, 3M, 12M)
        vol_target: Annualized volatility target for signal scaling

    Returns:
        TSMOMSignal with signal, strength, and consensus
    """
    if lookbacks is None:
        lookbacks = [21, 63, 252]

    lookback_returns = {}
    signals = {}

    for lb in lookbacks:
        ret = close / close.shift(lb) - 1
        lookback_returns[f"{lb}d"] = ret
        signals[f"{lb}d"] = np.sign(ret)

    signal_df = pd.DataFrame(signals)
    consensus = signal_df.mean(axis=1)

    final_signal = np.sign(consensus)
    strength = consensus.abs()

    realized_vol = close.pct_change(fill_method=None).rolling(21).std() * np.sqrt(252)
    vol_scale = vol_target / realized_vol.clip(lower=0.01)
    vol_scale = vol_scale.clip(upper=2.0)

    return TSMOMSignal(
        signal=final_signal,
        strength=strength * vol_scale,
        lookback_returns=lookback_returns,
        consensus=consensus,
    )

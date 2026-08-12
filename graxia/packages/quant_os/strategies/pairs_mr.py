"""
Pairs Mean-Reversion signal.
Trade the spread between correlated pairs.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class PairsMRSignal:
    """Pairs mean-reversion signal result."""

    signal: pd.Series  # Signal: -1, 0, +1
    zscore: pd.Series  # Spread z-score
    spread: pd.Series  # Raw spread
    half_life: float  # Mean-reversion half-life


def compute_pairs_mr_signal(
    price_a: pd.Series,
    price_b: pd.Series,
    lookback: int = 60,
    entry_z: float = 2.0,
    exit_z: float = 0.5,
) -> PairsMRSignal:
    """
    Compute pairs mean-reversion signal.

    Args:
        price_a: Price series for asset A
        price_b: Price series for asset B
        lookback: Lookback period for z-score calculation
        entry_z: Z-score threshold for entry
        exit_z: Z-score threshold for exit

    Returns:
        PairsMRSignal with signal and diagnostics
    """
    spread = np.log(price_a / price_b)

    spread_mean = spread.rolling(lookback).mean()
    spread_std = spread.rolling(lookback).std()
    zscore = (spread - spread_mean) / spread_std.clip(lower=0.01)

    # Half-life estimation (Ornstein-Uhlenbeck)
    spread_diff = spread.diff()
    spread_lag = spread.shift(1)

    valid = spread_diff.notna() & spread_lag.notna()
    if valid.sum() > 10:
        theta = np.polyfit(spread_lag[valid], spread_diff[valid], 1)[0]
        half_life = -np.log(2) / np.log(1 + theta) if theta < 0 else np.inf
    else:
        half_life = np.nan

    signal = pd.Series(0.0, index=price_a.index)
    in_position = 0
    for i in range(len(zscore)):
        z = zscore.iloc[i]
        if pd.isna(z):
            continue
        if in_position == 0:
            if z > entry_z:
                in_position = -1  # Spread high -> short A, long B
            elif z < -entry_z:
                in_position = 1   # Spread low -> long A, short B
        elif in_position == -1 and z < exit_z:
            in_position = 0
        elif in_position == 1 and z > -exit_z:
            in_position = 0
        signal.iloc[i] = in_position

    return PairsMRSignal(
        signal=signal,
        zscore=zscore,
        spread=spread,
        half_life=half_life,
    )

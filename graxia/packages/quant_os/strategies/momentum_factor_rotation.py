"""
Momentum Factor Rotation â€” Multi-asset TSMOM rotation strategy.

Trial #1013 in the quant_os edge-search ledger.

ECONOMIC RATIONALE
==================
Cross-sectional momentum (Jegadeesh & Titman 1993) applied to a basket
of tradeable assets. Instead of trading a single instrument's trend,
we rank assets by their TSMOM signal strength and go long the top
performers while avoiding (or shorting) the laggards.

This captures the momentum risk premium across asset classes:
- When gold trends strongly â†’ long gold
- When gold stalls but silver trends â†’ rotate to silver
- Diversification across uncorrelated momentum factors

Uses existing TSMOM signal (strategies/tsmom.py) as building block.

PRE-REGISTERED PARAMETERS (FROZEN)
===================================
- lookbacks         = [21, 63, 252]  (multi-timeframe TSMOM)
- vol_target        = 0.10           (vol scaling target)
- top_n             = 2              (long top N assets)
- bottom_n          = 0              (short bottom N; 0 = long-only)
- rebalance_freq    = 5              (rebalance every N bars)
- min_signal_strength = 0.3          (min TSMOM strength to trade)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple

import numpy as np
import pandas as pd

from .tsmom import compute_tsmom_signal


# ---------------------------------------------------------------------------
# Frozen configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MomentumFactorRotationConfig:
    """Pre-registered configuration for Momentum Factor Rotation."""

    lookbacks: tuple[int, ...] = (21, 63, 252)
    vol_target: float = 0.10
    top_n: int = 2
    bottom_n: int = 0
    rebalance_freq: int = 5
    min_signal_strength: float = 0.3


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


class MomentumFactorRotationResult(NamedTuple):
    """Output of compute_momentum_factor_rotation()."""

    signal: pd.DataFrame  # {asset: signal {-1, 0, +1}}
    strength: pd.DataFrame  # {asset: strength 0-1}
    rank: pd.DataFrame  # {asset: rank 1..N}
    config: MomentumFactorRotationConfig


# ---------------------------------------------------------------------------
# Core signal computation
# ---------------------------------------------------------------------------


def compute_momentum_factor_rotation(
    prices: pd.DataFrame,
    config: MomentumFactorRotationConfig | None = None,
) -> MomentumFactorRotationResult:
    """Compute Momentum Factor Rotation signals across multiple assets.

    Mechanism
    ---------
    1. For each asset, compute multi-timeframe TSMOM signal + strength.
    2. Rank assets by TSMOM strength (descending).
    3. Every rebalance_freq bars:
         - Go LONG top_n assets (if strength > min_signal_strength)
         - Go SHORT bottom_n assets (if bottom_n > 0)
         - All others get signal = 0
    4. Hold until next rebalance.

    Parameters
    ----------
    prices : pd.DataFrame with columns = asset names, index = DatetimeIndex.
             Each column is a close price series.
    config : frozen MomentumFactorRotationConfig; defaults to pre-registered values.

    Returns
    -------
    MomentumFactorRotationResult with signal, strength, rank DataFrames.
    """
    if config is None:
        config = MomentumFactorRotationConfig()

    if prices.empty or len(prices.columns) == 0:
        empty_df = pd.DataFrame(dtype=int)
        return MomentumFactorRotationResult(
            signal=empty_df,
            strength=empty_df.astype(float),
            rank=empty_df.astype(float),
            config=config,
        )

    # 1) Compute TSMOM for each asset
    all_signals = pd.DataFrame(index=prices.index)
    all_strengths = pd.DataFrame(index=prices.index)

    for col in prices.columns:
        ts = compute_tsmom_signal(
            prices[col],
            lookbacks=list(config.lookbacks),
            vol_target=config.vol_target,
        )
        all_signals[col] = ts.signal
        all_strengths[col] = ts.strength

    # 2) Rank assets by strength (descending) at each bar
    # Higher strength = better rank (1 = best)
    rank = all_strengths.rank(axis=1, ascending=False, method="min")

    # 3) Generate rotation signals
    rotation_signal = pd.DataFrame(0, index=prices.index, columns=prices.columns)

    for i in range(len(prices)):
        # Only rebalance every rebalance_freq bars
        if i % config.rebalance_freq != 0:
            # Copy previous signal
            if i > 0:
                rotation_signal.iloc[i] = rotation_signal.iloc[i - 1]
            continue

        bar_rank = rank.iloc[i]
        bar_strength = all_strengths.iloc[i]

        for col in prices.columns:
            r = bar_rank[col]
            s = bar_strength[col]

            if pd.isna(r) or pd.isna(s):
                continue

            if s < config.min_signal_strength:
                continue

            if r <= config.top_n:
                rotation_signal.loc[rotation_signal.index[i], col] = 1
            elif config.bottom_n > 0 and r > len(prices.columns) - config.bottom_n:
                rotation_signal.loc[rotation_signal.index[i], col] = -1

    # Forward-fill signals between rebalances
    rotation_signal = rotation_signal.ffill()

    return MomentumFactorRotationResult(
        signal=rotation_signal.astype(int),
        strength=all_strengths,
        rank=rank,
        config=config,
    )


__all__ = [
    "MomentumFactorRotationConfig",
    "MomentumFactorRotationResult",
    "compute_momentum_factor_rotation",
]

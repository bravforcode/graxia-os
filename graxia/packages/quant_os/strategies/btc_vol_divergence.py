"""BTC Volume-Price Divergence (BTCVD) — trial #2001.

When BTC makes new 20-day high but volume < 80% of 20-day avg -> short.
When BTC makes new 20-day low but volume < 80% of 20-day avg -> long.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import NamedTuple
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BTCVolDivConfig:
    price_window: int = 20
    vol_window: int = 20
    vol_threshold: float = 0.8
    hold_days: int = 5
    atr_period: int = 14
    stop_atr: float = 2.0


class BTCVolDivResult(NamedTuple):
    signal: pd.Series
    vol_ratio: pd.Series
    price_extreme: pd.Series
    config: BTCVolDivConfig


def _atr(highs: pd.Series, lows: pd.Series, closes: pd.Series, period: int) -> pd.Series:
    tr = pd.concat([highs - lows, (highs - closes.shift(1)).abs(), (lows - closes.shift(1)).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def compute_btcvd_signals(
    close: pd.Series,
    highs: pd.Series,
    lows: pd.Series,
    volume: pd.Series,
    config: BTCVolDivConfig | None = None,
) -> BTCVolDivResult:
    config = config or BTCVolDivConfig()

    price_high_roll = highs.rolling(config.price_window).max().shift(1)
    price_low_roll = lows.rolling(config.price_window).min().shift(1)
    vol_avg = volume.rolling(config.vol_window).mean().shift(1)
    vol_ratio = volume / vol_avg.replace(0, np.nan)

    # New high + low volume = weak rally = short
    new_high = highs >= price_high_roll
    vol_weak = vol_ratio < config.vol_threshold
    short_signal = new_high & vol_weak

    # New low + low volume = weak selloff = long
    new_low = lows <= price_low_roll
    long_signal = new_low & vol_weak

    signal = pd.Series(0, index=close.index, dtype=int, name="signal")
    signal[long_signal] = 1
    signal[short_signal] = -1

    # Apply hold period
    hold_counter = 0
    final_signal = pd.Series(0, index=close.index, dtype=int, name="signal")
    for i in range(len(signal)):
        if hold_counter > 0:
            hold_counter -= 1
            continue
        if signal.iloc[i] != 0:
            final_signal.iloc[i] = signal.iloc[i]
            hold_counter = config.hold_days

    price_extreme = pd.Series(0, index=close.index, dtype=int)
    price_extreme[new_high] = 1
    price_extreme[new_low] = -1

    return BTCVolDivResult(signal=final_signal, vol_ratio=vol_ratio, price_extreme=price_extreme, config=config)

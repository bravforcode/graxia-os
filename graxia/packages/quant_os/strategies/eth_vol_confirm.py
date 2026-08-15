"""ETH Volume Confirmation (ETHVC) â€” trial #2002.

When ETH price + volume both confirm (new 10-day high + volume > 80th pct) -> long.
When new 10-day low + high volume -> short.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import NamedTuple
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ETHVolConfirmConfig:
    price_window: int = 10
    vol_window: int = 10
    vol_confirm_pct: float = 80.0
    hold_days: int = 3
    atr_period: int = 14
    stop_atr: float = 2.0


class ETHVolConfirmResult(NamedTuple):
    signal: pd.Series
    vol_percentile: pd.Series
    price_confirm: pd.Series
    config: ETHVolConfirmConfig


def compute_ethvc_signals(
    close: pd.Series,
    highs: pd.Series,
    lows: pd.Series,
    volume: pd.Series,
    config: ETHVolConfirmConfig | None = None,
) -> ETHVolConfirmResult:
    config = config or ETHVolConfirmConfig()

    price_high_roll = highs.rolling(config.price_window).max().shift(1)
    price_low_roll = lows.rolling(config.price_window).min().shift(1)

    # Volume percentile (rolling)
    vol_pct = volume.rolling(config.vol_window).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1] * 100, raw=False).shift(1)
    vol_confirm = vol_pct > config.vol_confirm_pct

    # Price confirmation
    new_high = highs >= price_high_roll
    new_low = lows <= price_low_roll

    # Strong moves: price + volume confirm
    long_signal = new_high & vol_confirm
    short_signal = new_low & vol_confirm

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

    price_confirm = pd.Series(0, index=close.index, dtype=int)
    price_confirm[new_high] = 1
    price_confirm[new_low] = -1

    return ETHVolConfirmResult(signal=final_signal, vol_percentile=vol_pct, price_confirm=price_confirm, config=config)

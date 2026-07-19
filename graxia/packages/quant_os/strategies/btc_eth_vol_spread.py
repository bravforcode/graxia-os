"""BTC-ETH Volume Divergence Spread (BEVS) â€” trial #2003.

When BTC volume diverges from ETH volume (BTC high + ETH low) -> long BTC, short ETH.
When opposite -> short BTC, long ETH.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import NamedTuple
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BTCETHVolSpreadConfig:
    vol_window: int = 15
    divergence_threshold: float = 0.3
    hold_days: int = 5
    atr_period: int = 14
    stop_atr: float = 2.0


class BEVSResult(NamedTuple):
    signal: pd.Series
    vol_divergence: pd.Series
    config: BTCETHVolSpreadConfig


def compute_bevs_signals(
    btc_close: pd.Series,
    btc_volume: pd.Series,
    eth_close: pd.Series,
    eth_volume: pd.Series,
    config: BTCETHVolSpreadConfig | None = None,
) -> BEVSResult:
    config = config or BTCETHVolSpreadConfig()

    # Normalize volumes to z-scores
    btc_vol_z = (btc_volume - btc_volume.rolling(config.vol_window).mean()) / btc_volume.rolling(config.vol_window).std().replace(0, np.nan)
    eth_vol_z = (eth_volume - eth_volume.rolling(config.vol_window).mean()) / eth_volume.rolling(config.vol_window).std().replace(0, np.nan)

    # Divergence: BTC vol high + ETH vol low (or vice versa)
    divergence = btc_vol_z - eth_vol_z

    # Align by date (inner join on index)
    aligned = pd.concat({"btc_close": btc_close, "eth_close": eth_close, "divergence": divergence}, axis=1, join="inner").dropna()

    signal = pd.Series(0, index=aligned.index, dtype=int, name="signal")

    # BTC vol high + ETH vol low -> long BTC, short ETH (we signal long BTC)
    btc_long = aligned["divergence"] > config.divergence_threshold
    # BTC vol low + ETH vol high -> short BTC, long ETH (we signal short BTC)
    btc_short = aligned["divergence"] < -config.divergence_threshold

    signal[btc_long] = 1
    signal[btc_short] = -1

    # Apply hold period
    hold_counter = 0
    final_signal = pd.Series(0, index=aligned.index, dtype=int, name="signal")
    for i in range(len(signal)):
        if hold_counter > 0:
            hold_counter -= 1
            continue
        if signal.iloc[i] != 0:
            final_signal.iloc[i] = signal.iloc[i]
            hold_counter = config.hold_days

    return BEVSResult(signal=final_signal, vol_divergence=divergence, config=config)

"""
Orderflow Imbalance — Microstructure signal from M15 OHLCV.

Trial #1012 in the quant_os edge-search ledger.

ECONOMIC RATIONALE
==================
Without Level 2 orderbook data, we approximate orderflow imbalance using
the Close Location Value (CLV) methodology:

CLV = ((Close - Low) - (High - Close)) / (High - Low)

- CLV near +1: buying pressure (close near high)
- CLV near -1: selling pressure (close near low)

Cumulative CLV over N bars reveals sustained buying/selling pressure
that precedes directional moves. This is a microstructure signal that
captures informed trader activity before it shows up in price trends.

PRE-REGISTERED PARAMETERS (FROZEN)
===================================
- clv_window        = 10    (rolling CLV sum window)
- entry_threshold   = 5.0   (cumulative CLV for entry)
- exit_threshold    = 1.0   (cumulative CLV for exit)
- atr_period        = 14    (ATR for stop sizing)
- stop_atr          = 2.0   (stop-loss in ATR multiples)
- min_bars          = 50    (minimum bars before signal)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Frozen configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OrderflowImbalanceConfig:
    """Pre-registered configuration for Orderflow Imbalance strategy."""

    clv_window: int = 10
    entry_threshold: float = 5.0
    exit_threshold: float = 1.0
    atr_period: int = 14
    stop_atr: float = 2.0
    min_bars: int = 50


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


class OrderflowImbalanceResult(NamedTuple):
    """Output of compute_orderflow_imbalance_signals()."""

    signal: pd.Series
    clv: pd.Series
    cum_clv: pd.Series
    config: OrderflowImbalanceConfig


# ---------------------------------------------------------------------------
# Core signal computation
# ---------------------------------------------------------------------------


def compute_orderflow_imbalance_signals(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    config: OrderflowImbalanceConfig | None = None,
) -> OrderflowImbalanceResult:
    """Compute Orderflow Imbalance signals from OHLCV data.

    Mechanism
    ---------
    1. Compute Close Location Value (CLV) per bar:
         CLV = ((Close - Low) - (High - Close)) / (High - Low)
    2. Cumulative CLV over clv_window bars.
    3. Entry:
         - cum_CLV > entry_threshold  →  LONG (sustained buying pressure)
         - cum_CLV < -entry_threshold →  SHORT (sustained selling pressure)
    4. Exit when cum_CLV reverts past exit_threshold.
    5. Minimum bars filter to avoid noise.

    Parameters
    ----------
    open_, high, low, close : pd.Series of OHLCV data.
    config : frozen OrderflowImbalanceConfig; defaults to pre-registered values.

    Returns
    -------
    OrderflowImbalanceResult with signal, clv, cum_clv, config.
    """
    if config is None:
        config = OrderflowImbalanceConfig()

    df = pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
    }).dropna()

    if len(df) < config.min_bars:
        empty = pd.Series(0, index=df.index, dtype=int, name="signal")
        return OrderflowImbalanceResult(
            signal=empty,
            clv=pd.Series(np.nan, index=df.index),
            cum_clv=pd.Series(np.nan, index=df.index),
            config=config,
        )

    # 1) CLV per bar
    hl_range = (df["high"] - df["low"]).replace(0, np.nan)
    clv = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / hl_range
    clv = clv.fillna(0)
    clv.name = "clv"

    # 2) Cumulative CLV (rolling sum)
    cum_clv = clv.rolling(window=config.clv_window, min_periods=config.clv_window).sum()
    cum_clv.name = "cum_clv"

    # 3) Signal generation with state machine
    signal = pd.Series(0, index=df.index, dtype=int, name="signal")
    in_position = 0

    for i in range(len(df)):
        if i < config.min_bars:
            continue

        c = cum_clv.iloc[i]
        if pd.isna(c):
            continue

        if in_position == 0:
            if c > config.entry_threshold:
                in_position = 1
            elif c < -config.entry_threshold:
                in_position = -1
        elif in_position == 1:
            if c < config.exit_threshold:
                in_position = 0
        elif in_position == -1:
            if c > -config.exit_threshold:
                in_position = 0

        signal.iloc[i] = in_position

    return OrderflowImbalanceResult(
        signal=signal,
        clv=clv,
        cum_clv=cum_clv,
        config=config,
    )


__all__ = [
    "OrderflowImbalanceConfig",
    "OrderflowImbalanceResult",
    "compute_orderflow_imbalance_signals",
]

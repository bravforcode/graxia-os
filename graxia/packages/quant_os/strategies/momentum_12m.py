"""
Momentum 12M Strategy (TSMOM)
==============================
Moskowitz, Ooi, Pedersen (2012): Time-series momentum.

Signal: sign of 252-bar (12-month) cumulative return.
Exit: ATR-based SL/TP.

This is the ACTUAL strategy for backtest engine — not the toy simulation
(signal * returns * vol_mult + noise) used in pipeline scripts.
"""

from decimal import Decimal
from typing import Any

import numpy as np

from ..core.enums import RegimeType, SignalType
from .base import Signal, Strategy, StrategyConfig


class Momentum12M(Strategy):
    """Time-Series Momentum with 252-bar lookback."""

    def __init__(
        self,
        lookback: int = 252,
        atr_period: int = 14,
        atr_sl_mult: float = 2.0,
        atr_tp_mult: float = 3.0,
    ):
        config = StrategyConfig(
            name="Momentum12M",
            version="1.0",
            symbols=["XAUUSD"],
            timeframes=["D1"],
            risk_per_trade_pct=1.0,
            max_trades_per_day=1,
            min_confidence=0.0,
            min_risk_reward=0.0,
            require_trend_confirm=False,
        )
        super().__init__(config)
        self.lookback = lookback
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult

    def required_features(self) -> list[str]:
        return [f"ema_{self.atr_period}"]  # minimal — we compute inline

    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict[str, Any] | None = None,
        regime: RegimeType | None = None,
        **kwargs,
    ) -> Signal | None:
        close = ohlcv_data.get("close", [])
        high = ohlcv_data.get("high", [])
        low = ohlcv_data.get("low", [])

        if len(close) < self.lookback + self.atr_period + 1:
            return None

        current_price = float(close[-1])

        # ── Momentum signal: sign of 252-bar return ──
        lookback_return = current_price / float(close[-self.lookback - 1]) - 1.0
        if lookback_return == 0:
            return None

        direction = 1 if lookback_return > 0 else -1

        # ── ATR for SL/TP ──
        atr_vals = []
        for j in range(-self.atr_period, 0):
            tr = max(
                float(high[j]) - float(low[j]),
                abs(float(high[j]) - float(close[j - 1])),
                abs(float(low[j]) - float(close[j - 1])),
            )
            atr_vals.append(tr)
        atr = sum(atr_vals) / len(atr_vals)

        if atr <= 0:
            return None

        entry_price = Decimal(str(current_price))
        if direction == 1:
            stop_loss = Decimal(str(current_price - self.atr_sl_mult * atr))
            take_profit = Decimal(str(current_price + self.atr_tp_mult * atr))
            signal_type = SignalType.BUY
        else:
            stop_loss = Decimal(str(current_price + self.atr_sl_mult * atr))
            take_profit = Decimal(str(current_price - self.atr_tp_mult * atr))
            signal_type = SignalType.SELL

        return Signal.create(
            strategy_id=self.id,
            symbol=symbol,
            signal_type=signal_type,
            confidence=abs(lookback_return),
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

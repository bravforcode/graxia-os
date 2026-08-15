"""
Hybrid Momentum-MeanReversion Strategy
========================================
Toy simulation used pure momentum: sign(60-bar mean return).
Real engine uses same signal with ATR-based exits.
"""

from decimal import Decimal
from typing import Any

import numpy as np

from ..core.enums import RegimeType, SignalType
from .base import Signal, Strategy, StrategyConfig


class HybridMomMR(Strategy):
    """Hybrid Momentum/MeanReversion (toy sim was pure momentum)."""

    def __init__(
        self,
        lookback: int = 60,
        atr_period: int = 14,
        atr_sl_mult: float = 2.0,
        atr_tp_mult: float = 3.0,
    ):
        config = StrategyConfig(
            name="HybridMomMR",
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
        return []

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

        # Signal: sign of mean return over lookback (pure momentum per toy sim)
        returns = [float(close[i]) / float(close[i - 1]) - 1.0 for i in range(-self.lookback, 0)]
        mean_ret = np.mean(returns)

        if mean_ret == 0:
            return None

        direction = 1 if mean_ret > 0 else -1

        # ATR for SL/TP
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
            confidence=abs(mean_ret),
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

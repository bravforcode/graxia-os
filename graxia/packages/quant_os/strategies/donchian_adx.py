"""
Donchian Channel Breakout + ADX Trend Filter
=============================================
Only enters Donchian breakouts when ADX > threshold (confirmed trend).
Reduces false breakouts in ranging markets.

Exit: ATR-based SL/TP.
"""

from decimal import Decimal
from typing import Any

import numpy as np

from ..core.enums import RegimeType, SignalType
from .base import Signal, Strategy, StrategyConfig


class DonchianADX(Strategy):
    """Donchian breakout with ADX trend filter."""

    def __init__(
        self,
        period: int = 10,
        atr_period: int = 14,
        atr_sl_mult: float = 2.0,
        atr_tp_mult: float = 3.0,
        adx_period: int = 14,
        adx_threshold: float = 25.0,
    ):
        config = StrategyConfig(
            name=f"DonchianADX_{period}_adx{int(adx_threshold)}",
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
        self.period = period
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold

    def required_features(self) -> list[str]:
        return [f"donchian_{self.period}", f"adx_{self.adx_period}"]

    def _compute_adx(self, high: list, low: list, close: list) -> float | None:
        """Compute ADX using Wilder smoothing."""
        n = len(close)
        if n < self.adx_period * 2 + 1:
            return None

        # True Range
        tr = []
        plus_dm = []
        minus_dm = []
        for i in range(1, n):
            hl = float(high[i]) - float(low[i])
            hc = abs(float(high[i]) - float(close[i - 1]))
            lc = abs(float(low[i]) - float(close[i - 1]))
            tr.append(max(hl, hc, lc))

            up = float(high[i]) - float(high[i - 1])
            down = float(low[i - 1]) - float(low[i])
            plus_dm.append(up if up > down and up > 0 else 0.0)
            minus_dm.append(down if down > up and down > 0 else 0.0)

        # Wilder smoothing
        atr = sum(tr[: self.adx_period])
        plus_di_smooth = sum(plus_dm[: self.adx_period])
        minus_di_smooth = sum(minus_dm[: self.adx_period])

        dx_values = []
        for i in range(self.adx_period, len(tr)):
            atr = atr - atr / self.adx_period + tr[i]
            plus_di_smooth = plus_di_smooth - plus_di_smooth / self.adx_period + plus_dm[i]
            minus_di_smooth = minus_di_smooth - minus_di_smooth / self.adx_period + minus_dm[i]

            if atr == 0:
                continue
            plus_di = 100 * plus_di_smooth / atr
            minus_di = 100 * minus_di_smooth / atr

            if plus_di + minus_di == 0:
                dx = 0.0
            else:
                dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
            dx_values.append(dx)

        if len(dx_values) < self.adx_period:
            return None

        adx = sum(dx_values[: self.adx_period]) / self.adx_period
        for dx in dx_values[self.adx_period:]:
            adx = (adx * (self.adx_period - 1) + dx) / self.adx_period

        return adx

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

        min_bars = max(self.period, self.adx_period * 2 + 1) + self.atr_period + 2
        if len(close) < min_bars:
            return None

        current_price = float(close[-1])

        # Donchian channel from prior `period` bars
        hh = max(float(h) for h in high[-self.period - 1 : -1])
        ll = min(float(l) for l in low[-self.period - 1 : -1])

        direction = 0
        if current_price > hh:
            direction = 1
        elif current_price < ll:
            direction = -1
        if direction == 0:
            return None

        # ADX filter
        adx = self._compute_adx(high, low, close)
        if adx is None or adx < self.adx_threshold:
            return None

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

        breakout_edge = hh if direction == 1 else ll
        breakout_strength = abs(current_price - breakout_edge) / current_price

        return Signal.create(
            strategy_id=self.id,
            symbol=symbol,
            signal_type=signal_type,
            confidence=min(breakout_strength * 10, 1.0),
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

"""
Donchian Channel Breakout Strategy
===================================
Classic channel breakout: long on new N-bar high, short on new N-bar low.
Optional volatility filter (skip breakouts in low-vol regimes).
Exit: ATR-based SL/TP.

This is the ACTUAL strategy for backtest engine â€” not the toy simulation
(signal * returns * vol_mult + noise) used in pipeline scripts.
"""

from decimal import Decimal
from typing import Any

import numpy as np

from ..core.enums import RegimeType, SignalType
from .base import Signal, Strategy, StrategyConfig


class DonchianBreakout(Strategy):
    """Donchian channel breakout with optional ATR-ratio volatility filter."""

    def __init__(
        self,
        period: int = 20,
        atr_period: int = 14,
        atr_sl_mult: float = 2.0,
        atr_tp_mult: float = 3.0,
        vol_filter: bool = True,
        vol_filter_pctile: float = 0.7,
        vol_lookback: int = 200,
    ):
        config = StrategyConfig(
            name=f"DonchianBreakout{period}",
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
        self.vol_filter = vol_filter
        self.vol_filter_pctile = vol_filter_pctile
        self.vol_lookback = vol_lookback

    def required_features(self) -> list[str]:
        return [f"donchian_{self.period}"]  # minimal â€” we compute inline

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

        min_bars = self.period + self.atr_period + 2
        if len(close) < min_bars:
            return None

        current_price = float(close[-1])

        # â”€â”€ Donchian channel from prior `period` bars (excludes current bar) â”€â”€
        hh = max(float(h) for h in high[-self.period - 1 : -1])
        ll = min(float(l) for l in low[-self.period - 1 : -1])

        direction = 0
        if current_price > hh:
            direction = 1
        elif current_price < ll:
            direction = -1
        if direction == 0:
            return None

        # â”€â”€ ATR for vol filter + SL/TP â”€â”€
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

        # â”€â”€ Volatility filter: current TR/price ratio vs trailing median â”€â”€
        if self.vol_filter:
            lookback = min(self.vol_lookback, len(close) - 1)
            hist_ratios = [
                abs(float(high[k]) - float(low[k])) / float(close[k])
                for k in range(len(close) - lookback, len(close) - 1)
                if float(close[k]) > 0
            ]
            if hist_ratios:
                median_ratio = float(np.median(hist_ratios))
                current_ratio = (float(high[-1]) - float(low[-1])) / current_price
                if current_ratio < median_ratio * self.vol_filter_pctile:
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

"""
Donchian Channel Breakout + RSI Momentum Filter
=================================================
Hybrid breakout strategy: enter on Donchian channel breakout, confirmed by RSI
not being in overbought/oversold territory. Reduces false breakouts in ranging
markets where price oscillates at channel boundaries.

Rules:
  Entry Long:  Price > Donchian Upper AND RSI(14) < overbought_threshold
  Entry Short: Price < Donchian Lower AND RSI(14) > oversold_threshold
  Exit: ATR-based SL/TP (identical to donchian.py / donchian_adx.py)

This is a CANDIDATE strategy — untested until validated via pooled DK-test.

Reference: Donchian (1960), Welles Wilder (1978).
"""

from decimal import Decimal
from typing import Any

import numpy as np

from ..core.enums import RegimeType, SignalType
from .base import Signal, Strategy, StrategyConfig


class DonchianRSI(Strategy):
    """Donchian breakout with RSI momentum filter."""

    def __init__(
        self,
        period: int = 20,
        atr_period: int = 14,
        atr_sl_mult: float = 2.0,
        atr_tp_mult: float = 3.0,
        rsi_period: int = 14,
        rsi_overbought: float = 70.0,
        rsi_oversold: float = 30.0,
        vol_filter: bool = True,
        vol_filter_pctile: float = 0.7,
        vol_lookback: int = 200,
    ):
        config = StrategyConfig(
            name=f"DonchianRSI_{period}_rsi{int(rsi_overbought)}",
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
        self.rsi_period = rsi_period
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold
        self.vol_filter = vol_filter
        self.vol_filter_pctile = vol_filter_pctile
        self.vol_lookback = vol_lookback

    def required_features(self) -> list[str]:
        return [f"donchian_{self.period}", f"rsi_{self.rsi_period}"]

    # ── RSI calculation (Wilder smoothing) ────────────────────────
    @staticmethod
    def _compute_rsi(closes: list, period: int) -> float | None:
        """Compute RSI using Wilder's smoothing method. Returns latest RSI or None."""
        if len(closes) < period + 2:
            return None

        gains = []
        losses = []
        for i in range(1, period + 1):
            change = float(closes[i]) - float(closes[i - 1])
            gains.append(max(change, 0.0))
            losses.append(max(-change, 0.0))

        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        for i in range(period + 1, len(closes)):
            change = float(closes[i]) - float(closes[i - 1])
            gain = max(change, 0.0)
            loss = max(-change, 0.0)
            avg_gain = (avg_gain * (period - 1) + gain) / period
            avg_loss = (avg_loss * (period - 1) + loss) / period

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

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

        min_bars = max(self.period, self.rsi_period + 2) + self.atr_period + 2
        if len(close) < min_bars:
            return None

        current_price = float(close[-1])

        # ── Donchian channel from prior `period` bars (excludes current bar) ──
        hh = max(float(h) for h in high[-self.period - 1 : -1])
        ll = min(float(l) for l in low[-self.period - 1 : -1])

        direction = 0
        if current_price > hh:
            direction = 1
        elif current_price < ll:
            direction = -1
        if direction == 0:
            return None

        # ── RSI filter: confirm momentum is not exhausted ──
        rsi = self._compute_rsi(close, self.rsi_period)
        if rsi is None:
            return None

        # Long breakout rejected if RSI already overbought
        if direction == 1 and rsi >= self.rsi_overbought:
            return None
        # Short breakout rejected if RSI already oversold
        if direction == -1 and rsi <= self.rsi_oversold:
            return None

        # ── ATR for vol filter + SL/TP ──
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

        # ── Volatility filter: current TR/price ratio vs trailing median ──
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

"""
RSI Mean-Reversion Strategy
============================
Counter-trend (mean-reversion) hypothesis: buy oversold, sell overbought.

Signal:
  - RSI(14) < oversold_threshold â†’ BUY (expect bounce back up)
  - RSI(14) > overbought_threshold â†’ SELL (expect pullback down)
  - Optional EMA confirmation filter (price must be above/below EMA).

Exit: ATR-based SL/TP (identical to momentum_12m / donchian).

Reference: Welles Wilder (1978) â€” Relative Strength Index.
"""

from decimal import Decimal
from typing import Any

import numpy as np

from ..core.enums import RegimeType, SignalType
from .base import Signal, Strategy, StrategyConfig


class RSIMeanReversion(Strategy):
    """RSI-based mean-reversion strategy with ATR SL/TP."""

    def __init__(
        self,
        rsi_period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
        ema_period: int = 0,
        atr_period: int = 14,
        atr_sl_mult: float = 2.0,
        atr_tp_mult: float = 3.0,
    ):
        config = StrategyConfig(
            name=f"RSIMeanReversion_{int(oversold)}_{int(overbought)}",
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
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.ema_period = ema_period  # 0 = disabled
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult

    def required_features(self) -> list[str]:
        features = [f"rsi_{self.rsi_period}"]
        if self.ema_period > 0:
            features.append(f"ema_{self.ema_period}")
        return features

    # â”€â”€ RSI calculation (Wilder smoothing) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    @staticmethod
    def _compute_rsi(closes: list, period: int) -> float | None:
        """Compute RSI using Wilder's smoothing method. Returns latest RSI or None."""
        if len(closes) < period + 2:
            return None

        # Initial average gain/loss from first `period` price changes
        gains = []
        losses = []
        for i in range(1, period + 1):
            change = float(closes[i]) - float(closes[i - 1])
            gains.append(max(change, 0.0))
            losses.append(max(-change, 0.0))

        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        # Wilder smoothing for subsequent bars
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

    # â”€â”€ EMA calculation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    @staticmethod
    def _compute_ema(closes: list, period: int) -> float | None:
        """Compute EMA of closes. Returns latest value or None."""
        if len(closes) < period:
            return None
        k = 2.0 / (period + 1)
        ema = float(closes[0])
        for c in closes[1:]:
            ema = float(c) * k + ema * (1.0 - k)
        return ema

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

        # Need rsi_period+1 closes for first RSI, plus atr_period for ATR
        min_bars = self.rsi_period + 2 + self.atr_period
        if len(close) < min_bars:
            return None

        current_price = float(close[-1])

        # â”€â”€ RSI signal â”€â”€
        rsi = self._compute_rsi(close, self.rsi_period)
        if rsi is None:
            return None

        direction = 0
        if rsi < self.oversold:
            direction = 1  # BUY â€” oversold, expect bounce
        elif rsi > self.overbought:
            direction = -1  # SELL â€” overbought, expect pullback

        if direction == 0:
            return None

        # â”€â”€ Optional EMA confirmation filter â”€â”€
        if self.ema_period > 0:
            ema = self._compute_ema(close, self.ema_period)
            if ema is None:
                return None
            # BUY requires price > EMA (mean-reversion in uptrend); SELL requires price < EMA
            if direction == 1 and current_price < ema:
                return None
            if direction == -1 and current_price > ema:
                return None

        # â”€â”€ ATR for SL/TP â”€â”€
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

        # Confidence: how extreme the RSI reading is
        if direction == 1:
            confidence = min((self.oversold - rsi) / self.oversold, 1.0)
        else:
            confidence = min((rsi - self.overbought) / (100.0 - self.overbought), 1.0)

        return Signal.create(
            strategy_id=self.id,
            symbol=symbol,
            signal_type=signal_type,
            confidence=max(confidence, 0.01),
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

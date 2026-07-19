"""
Bollinger Band Squeeze Breakout Strategy
=========================================
Enter when BB bandwidth narrows (squeeze) then expands (breakout).
Classic volatility-expansion play.

Squeeze detection: BB width < N-period percentile threshold.
Breakout: close above upper BB (buy) or below lower BB (sell).
Exit: ATR-based SL/TP.
"""

from decimal import Decimal
from typing import Any

import numpy as np

from ..core.enums import RegimeType, SignalType
from .base import Signal, Strategy, StrategyConfig


class BollingerSqueeze(Strategy):
    """Bollinger Band squeeze breakout with ATR SL/TP."""

    def __init__(
        self,
        bb_period: int = 20,
        bb_std: float = 2.0,
        squeeze_lookback: int = 120,
        squeeze_pctile: float = 0.2,
        atr_period: int = 14,
        atr_sl_mult: float = 2.0,
        atr_tp_mult: float = 3.0,
    ):
        config = StrategyConfig(
            name=f"BBsqueeze_{bb_period}_p{int(squeeze_pctile*100)}",
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
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.squeeze_lookback = squeeze_lookback
        self.squeeze_pctile = squeeze_pctile
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult

    def required_features(self) -> list[str]:
        return [f"bb_{self.bb_period}", f"atr_{self.atr_period}"]

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

        min_bars = max(self.bb_period, self.squeeze_lookback) + self.atr_period + 2
        if len(close) < min_bars:
            return None

        current_price = float(close[-1])

        # Bollinger Bands
        closes_arr = np.array([float(c) for c in close[-self.bb_period:]])
        sma = float(closes_arr.mean())
        std = float(closes_arr.std(ddof=0))
        upper = sma + self.bb_std * std
        lower = sma - self.bb_std * std

        if std <= 0 or sma <= 0:
            return None

        bb_width = (upper - lower) / sma  # Normalized width

        # Squeeze detection: current width vs historical
        hist_widths = []
        for i in range(
            max(self.bb_period, len(close) - self.squeeze_lookback),
            len(close) - 1,
        ):
            window = np.array([float(close[i - self.bb_period + 1 + j]) for j in range(self.bb_period)])
            w_sma = float(window.mean())
            w_std = float(window.std(ddof=0))
            if w_sma > 0:
                hist_widths.append((w_std * self.bb_std * 2) / w_sma)

        if not hist_widths:
            return None

        threshold = float(np.percentile(hist_widths, self.squeeze_pctile * 100))

        # Previous bar was in squeeze (width < threshold), current bar breaks out
        prev_closes = [float(c) for c in close[-self.bb_period - 1: -1]]
        prev_sma = sum(prev_closes) / len(prev_closes)
        prev_std = (sum((c - prev_sma) ** 2 for c in prev_closes) / len(prev_closes)) ** 0.5
        prev_upper = prev_sma + self.bb_std * prev_std
        prev_lower = prev_sma - self.bb_std * prev_std
        prev_width = (prev_upper - prev_lower) / prev_sma if prev_sma > 0 else 999

    # If previous bar was NOT in squeeze, no signal
        if prev_width >= threshold:
            return None

        # Breakout direction
        direction = 0
        if current_price > upper:
            direction = 1  # Buy: broke above upper BB
        elif current_price < lower:
            direction = -1  # Sell: broke below lower BB

        if direction == 0:
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

        # Confidence: squeeze depth (how tight was the squeeze)
        squeeze_depth = max(0, 1.0 - prev_width / threshold) if threshold > 0 else 0.5

        return Signal.create(
            strategy_id=self.id,
            symbol=symbol,
            signal_type=signal_type,
            confidence=max(squeeze_depth, 0.01),
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

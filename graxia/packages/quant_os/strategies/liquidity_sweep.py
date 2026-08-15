"""Liquidity Sweep Strategy â€” wraps SweepClassifier for BacktestEngine parity.

This is the live strategy (regime/liquidity_sweep) adapted as a BacktestEngine
Strategy subclass so the SAME signal logic runs in both backtest and live.

P0-3 FIX: includes RegimeDetector + relaxed sweep thresholds for parity.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from ..core.enums import RegimeType, SignalType
from ..regime import RegimeDetector
from ..regime.liquidity_map import LiquidityLevel, LiquidityMap
from ..regime.sweep_classifier import SweepClassifier
from .base import Signal, Strategy, StrategyConfig


class LiquiditySweepStrategy(Strategy):
    """Adapter: SweepClassifier â†’ BacktestEngine Strategy interface.

    Includes RegimeDetector for parity with live pipeline.
    Relaxed thresholds for backtest signal generation.
    """

    def __init__(self, config: StrategyConfig | None = None):
        super().__init__(config or StrategyConfig(name="LiquiditySweep"))
        self._regime_detector = RegimeDetector()
        self._sweep_lookback = 20  # bars for swing detection

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
        if len(close) < 60:
            return None

        closes = [float(c) for c in close]
        highs = [float(h) for h in ohlcv_data.get("high", close)]
        lows = [float(l) for l in ohlcv_data.get("low", close)]

        # Phase 1: Regime detection
        # P0-5/P1-1 FIX: use engine-provided regime when available,
        # fall back to own detector when not (standalone mode)
        if regime is not None:
            regime_str = regime.name if hasattr(regime, "name") else str(regime)
        else:
            regime_result = self._regime_detector.detect(closes, highs, lows)
            regime_str = regime_result.regime
        if regime_str == "UNCLEAR":
            return None

        # Phase 2: Simplified sweep detection (parity with live SweepClassifier)
        lookback = self._sweep_lookback
        current_price = closes[-1]
        # P1-2/P1-3 FIX: exclude current bar from lookback window
        # min(lows[-lookback:]) includes lows[-1], making lows[-1] < min() impossible
        recent_low = min(lows[-(lookback + 1):-1])
        recent_high = max(highs[-(lookback + 1):-1])

        # Sweep below recent low + close above = BUY
        if lows[-1] < recent_low and closes[-1] > recent_low:
            atr = self._atr(closes[-20:], highs[-20:], lows[-20:])
            if atr <= 0:
                return None
            sl = Decimal(str(current_price - atr * 1.5))
            tp = Decimal(str(current_price + atr * 2.0))
            return Signal.create(
                strategy_id=self.id,
                symbol=symbol,
                signal_type=SignalType.BUY,
                confidence=0.6,
                entry_price=Decimal(str(current_price)),
                stop_loss=sl,
                take_profit=tp,
                regime=RegimeType.TREND_STRONG_UP if regime_str == "TREND_UP" else RegimeType.RANGE_BOUND,
            )

        # Sweep above recent high + close below = SELL
        if highs[-1] > recent_high and closes[-1] < recent_high:
            atr = self._atr(closes[-20:], highs[-20:], lows[-20:])
            if atr <= 0:
                return None
            sl = Decimal(str(current_price + atr * 1.5))
            tp = Decimal(str(current_price - atr * 2.0))
            return Signal.create(
                strategy_id=self.id,
                symbol=symbol,
                signal_type=SignalType.SELL,
                confidence=0.6,
                entry_price=Decimal(str(current_price)),
                stop_loss=sl,
                take_profit=tp,
                regime=RegimeType.TREND_STRONG_DOWN if regime_str == "TREND_DOWN" else RegimeType.RANGE_BOUND,
            )

        return None

    @staticmethod
    def _atr(closes: list, highs: list, lows: list, period: int = 14) -> float:
        if len(closes) < period + 1:
            return 0.0
        trs = []
        for i in range(1, len(closes)):
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
            trs.append(tr)
        if len(trs) < period:
            return 0.0
        return sum(trs[-period:]) / period

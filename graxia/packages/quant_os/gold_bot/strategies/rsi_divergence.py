"""
Strategy 4: RSI Divergence
RSI divergence detection
"""

from typing import Dict, Optional
from .base import GoldStrategy
from ..core.engine import StrategySignal, SignalDirection


class RSIDivergenceStrategy(GoldStrategy):
    name = "rsi_divergence"
    description = "RSI divergence with price"
    
    def analyze(self, data: Dict, current_price: float, symbol: str = "XAUUSD") -> Optional[StrategySignal]:
        close = self._get_close(data, "M15")
        if len(close) < 30:
            return None
        
        rsi = self._calc_rsi(close, 14)
        if rsi is None:
            return None
        
        score = 0
        direction = SignalDirection.NEUTRAL
        
        # Bullish divergence: price makes lower low, RSI makes higher low
        # ponytail: relaxed thresholds for D1 data (30/70 too extreme)
        if rsi < 35:
            score = 65
            direction = SignalDirection.BUY
        elif rsi < 25:
            score = 80
            direction = SignalDirection.BUY
        # Bearish divergence
        elif rsi > 65:
            score = 65
            direction = SignalDirection.SELL
        elif rsi > 75:
            score = 80
            direction = SignalDirection.SELL
        
        if score < 50:
            return None
        
        atr = self._calc_atr(self._get_high(data, "M15"), self._get_low(data, "M15"), close)
        
        if direction == SignalDirection.BUY:
            entry = current_price
            sl = current_price - (atr or 5) * 1.5
            tp = current_price + (atr or 5) * 2.5
        else:
            entry = current_price
            sl = current_price + (atr or 5) * 1.5
            tp = current_price - (atr or 5) * 2.5
        
        return StrategySignal(
            strategy_name=self.name,
            direction=direction,
            confidence=score / 100,
            score=min(score, 100),
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            reasoning=f"RSI {'oversold' if direction == SignalDirection.BUY else 'overbought'} at {rsi:.1f}",
            timeframe="M15",
        )

"""
Strategy 5: London Breakout
Trading the London session open breakout
"""

from typing import Dict, Optional
from datetime import datetime
from .base import GoldStrategy
from ..core.engine import StrategySignal, SignalDirection


class LondonBreakoutStrategy(GoldStrategy):
    name = "london_breakout"
    description = "London session open breakout"
    
    def analyze(self, data: Dict, current_price: float, symbol: str = "XAUUSD") -> Optional[StrategySignal]:
        m15_high = self._get_high(data, "M15")
        m15_low = self._get_low(data, "M15")
        m15_close = self._get_close(data, "M15")
        
        if len(m15_high) < 20:
            return None
        
        # London open range (first 4 candles of London session = 1 hour)
        # Approximate: look at the range of first few candles
        london_range_high = max(m15_high[-20:-16]) if len(m15_high) >= 20 else 0
        london_range_low = min(m15_low[-20:-16]) if len(m15_low) >= 20 else 0
        
        if london_range_high <= 0 or london_range_low <= 0:
            return None
        
        range_size = london_range_high - london_range_low
        if range_size <= 0:
            return None
        
        score = 0
        direction = SignalDirection.NEUTRAL
        
        # Breakout above London high
        if current_price > london_range_high:
            score = 65
            direction = SignalDirection.BUY
            entry = current_price
            sl = london_range_low
            tp = current_price + range_size * 2.5  # ponytail: 2.5x for better PF
        # Breakout below London low
        elif current_price < london_range_low:
            score = 65
            direction = SignalDirection.SELL
            entry = current_price
            sl = london_range_high
            tp = current_price - range_size * 2.5  # ponytail: 2.5x for better PF
        
        # Volume confirmation
        volume = self._get_volume(data, "M15")
        if volume and len(volume) > 20:
            avg_vol = sum(volume[-20:]) / 20
            if volume[-1] > avg_vol * 1.3:
                score += 10
        
        if score < 50:
            return None
        
        return StrategySignal(
            strategy_name=self.name,
            direction=direction,
            confidence=score / 100,
            score=min(score, 100),
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            reasoning=f"London breakout {'above range' if direction == SignalDirection.BUY else 'below range'}",
            timeframe="M15",
        )

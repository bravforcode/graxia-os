"""
Strategy 13: Opening Range Breakout ✦
Breakout from the first hour of trading
"""

from typing import Dict, Optional
from datetime import datetime
from .base import GoldStrategy
from ..core.engine import StrategySignal, SignalDirection


class OpeningRangeStrategy(GoldStrategy):
    name = "opening_range"
    description = "Opening range breakout"
    
    def analyze(self, data: Dict, current_price: float, symbol: str = "XAUUSD") -> Optional[StrategySignal]:
        high = self._get_high(data, "M5")
        low = self._get_low(data, "M5")
        close = self._get_close(data, "M5")
        volume = self._get_volume(data, "M5")
        
        if len(close) < 20 or not volume:
            return None
        
        # Opening range (first 12 M5 candles = 1 hour)
        or_high = max(high[:12]) if len(high) >= 12 else max(high)
        or_low = min(low[:12]) if len(low) >= 12 else min(low)
        
        or_range = or_high - or_low
        if or_range <= 0:
            return None
        
        score = 0
        direction = SignalDirection.NEUTRAL
        
        # Breakout above opening range
        if current_price > or_high:
            score = 70
            direction = SignalDirection.BUY
            entry = current_price
            sl = or_high - or_range * 0.3
            tp = current_price + or_range * 2.0  # ponytail: 2.0x for better PF
        # Breakout below opening range
        elif current_price < or_low:
            score = 70
            direction = SignalDirection.SELL
            entry = current_price
            sl = or_low + or_range * 0.3
            tp = current_price - or_range * 2.0  # ponytail: 2.0x for better PF
        
        # Volume confirmation
        avg_vol = sum(volume[-20:]) / 20 if len(volume) >= 20 else 1
        if volume[-1] > avg_vol * 1.3:
            score += 10
        
        # Time filter (only trade in first 4 hours)
        now = datetime.utcnow()
        if now.hour >= 12:
            score -= 20
        
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
            reasoning=f"Opening range {'breakout above' if direction == SignalDirection.BUY else 'breakdown below'}",
            timeframe="M5",
        )

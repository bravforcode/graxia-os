"""
Strategy 2: Supply & Demand
Identifies supply/demand zones from price action
"""

from typing import Dict, Optional
from .base import GoldStrategy
from ..core.engine import StrategySignal, SignalDirection


class SupplyDemandStrategy(GoldStrategy):
    name = "supply_demand"
    description = "Supply and Demand zone trading"
    min_timeframe = "M15"
    
    def analyze(self, data: Dict, current_price: float, symbol: str = "XAUUSD") -> Optional[StrategySignal]:
        m15_close = self._get_close(data, "M15")
        m15_high = self._get_high(data, "M15")
        m15_low = self._get_low(data, "M15")
        
        if len(m15_close) < 50:
            return None
        
        score = 0
        direction = SignalDirection.NEUTRAL
        
        # Find demand zone (cluster of lows)
        recent_lows = m15_low[-20:]
        avg_low = sum(recent_lows) / len(recent_lows)
        
        # Find supply zone (cluster of highs)
        recent_highs = m15_high[-20:]
        avg_high = sum(recent_highs) / len(recent_highs)
        
        zone_range = avg_high - avg_low
        
        if zone_range <= 0:
            return None
        
        # Price near demand zone
        if (current_price - avg_low) / zone_range < 0.2:
            score = 70
            direction = SignalDirection.BUY
            entry = current_price
            sl = avg_low - zone_range * 0.1
            tp = avg_high - zone_range * 0.1
        # Price near supply zone
        elif (avg_high - current_price) / zone_range < 0.2:
            score = 70
            direction = SignalDirection.SELL
            entry = current_price
            sl = avg_high + zone_range * 0.1
            tp = avg_low + zone_range * 0.1
        
        # Volume confirmation
        volume = self._get_volume(data, "M15")
        if volume and len(volume) > 20:
            avg_vol = sum(volume[-20:]) / 20
            if volume[-1] > avg_vol * 1.2:
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
            reasoning=f"Supply/Demand zone {'demand' if direction == SignalDirection.BUY else 'supply'}",
            timeframe="M15",
        )

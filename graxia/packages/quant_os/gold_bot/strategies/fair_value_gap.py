"""
Strategy 12: Fair Value Gap ✦
FVG detection and trading
"""

from typing import Dict, Optional
from .base import GoldStrategy
from ..core.engine import StrategySignal, SignalDirection


class FairValueGapStrategy(GoldStrategy):
    name = "fair_value_gap"
    description = "Fair Value Gap detection"
    
    def analyze(self, data: Dict, current_price: float, symbol: str = "XAUUSD") -> Optional[StrategySignal]:
        high = self._get_high(data, "M15")
        low = self._get_low(data, "M15")
        close = self._get_close(data, "M15")
        
        if len(close) < 20:
            return None
        
        score = 0
        direction = SignalDirection.NEUTRAL
        
        # Find FVGs (gap between candle 1 high and candle 3 low for bullish)
        # ponytail: wider window (25 bars) and smaller minimum gap for D1
        for i in range(len(high) - 3, max(0, len(high) - 25), -1):
            # Bullish FVG: candle 1 high < candle 3 low
            if low[i] > high[i+2]:
                fvg_top = low[i]
                fvg_bottom = high[i+2]
                fvg_mid = (fvg_top + fvg_bottom) / 2
                
                # Price is in the FVG zone (or within 5 points of it)
                if fvg_bottom - 5 <= current_price <= fvg_top + 5:
                    score = 75
                    direction = SignalDirection.BUY
                    entry = current_price
                    sl = fvg_bottom - 10  # ponytail: 10pt buffer
                    tp = current_price + (current_price - fvg_bottom) * 2.0
                    break
            
            # Bearish FVG: candle 1 low > candle 3 high
            if low[i+2] > high[i]:
                fvg_top = low[i+2]
                fvg_bottom = high[i]
                fvg_mid = (fvg_top + fvg_bottom) / 2
                
                if fvg_bottom - 5 <= current_price <= fvg_top + 5:
                    score = 75
                    direction = SignalDirection.SELL
                    entry = current_price
                    sl = fvg_top + 10  # ponytail: 10pt buffer
                    tp = current_price - (fvg_top - current_price) * 2.0
                    break
        
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
            reasoning=f"Fair Value Gap {'bullish' if direction == SignalDirection.BUY else 'bearish'}",
            timeframe="M15",
        )

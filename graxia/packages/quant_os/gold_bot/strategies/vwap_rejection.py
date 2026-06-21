"""
Strategy 7: VWAP Rejection
VWAP rejection with volume confirmation
"""

from typing import Dict, Optional
from .base import GoldStrategy
from ..core.engine import StrategySignal, SignalDirection


class VWAPRejectionStrategy(GoldStrategy):
    name = "vwap_rejection"
    description = "VWAP rejection with volume"
    
    def analyze(self, data: Dict, current_price: float, symbol: str = "XAUUSD") -> Optional[StrategySignal]:
        close = self._get_close(data, "M15")
        high = self._get_high(data, "M15")
        low = self._get_low(data, "M15")
        volume = self._get_volume(data, "M15")
        
        if len(close) < 20 or not volume:
            return None
        
        # Calculate VWAP (simplified)
        typical_price = [(high[i] + low[i] + close[i]) / 3 for i in range(len(close))]
        cum_tp_vol = [typical_price[i] * volume[i] for i in range(len(close))]
        cum_vol = [sum(volume[:i+1]) for i in range(len(volume))]
        
        vwap = cum_tp_vol[-1] / cum_vol[-1] if cum_vol[-1] > 0 else current_price
        
        # Distance from VWAP
        if vwap <= 0:
            return None
        distance = (current_price - vwap) / vwap * 100
        
        score = 0
        direction = SignalDirection.NEUTRAL
        
        # Rejection from VWAP (price came back after touching)
        if abs(distance) < 0.05:  # Within 0.05% of VWAP
            # Check if price was above and came back (bearish) or below and came back (bullish)
            prev_distance = (close[-2] - vwap) / vwap * 100 if len(close) > 1 else 0
            
            if prev_distance > 0.05 and distance <= 0.05:
                score = 70
                direction = SignalDirection.SELL
            elif prev_distance < -0.05 and distance >= -0.05:
                score = 70
                direction = SignalDirection.BUY
        
        # Volume confirmation
        avg_vol = sum(volume[-20:]) / 20 if len(volume) >= 20 else 1
        if volume[-1] > avg_vol * 1.2:
            score += 10
        
        if score < 50:
            return None
        
        atr = self._calc_atr(high, low, close)
        
        if direction == SignalDirection.BUY:
            entry = current_price
            sl = current_price - (atr or 5) * 1.5
            tp = current_price + (atr or 5) * 2.0
        else:
            entry = current_price
            sl = current_price + (atr or 5) * 1.5
            tp = current_price - (atr or 5) * 2.0
        
        return StrategySignal(
            strategy_name=self.name,
            direction=direction,
            confidence=score / 100,
            score=min(score, 100),
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            reasoning=f"VWAP rejection {'from above' if direction == SignalDirection.SELL else 'from below'}",
            timeframe="M15",
        )

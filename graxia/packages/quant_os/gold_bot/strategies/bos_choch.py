"""
Strategy 10: BOS/CHoCH
Break of Structure / Change of Character
"""

from typing import Dict, Optional
from .base import GoldStrategy
from ..core.engine import StrategySignal, SignalDirection


class BOSCHoCHStrategy(GoldStrategy):
    name = "bos_choch"
    description = "Break of Structure / Change of Character"
    
    def analyze(self, data: Dict, current_price: float, symbol: str = "XAUUSD") -> Optional[StrategySignal]:
        close = self._get_close(data, "M15")
        high = self._get_high(data, "M15")
        low = self._get_low(data, "M15")
        
        if len(close) < 30:
            return None
        
        # Find swing highs and lows
        # ponytail: 3-bar lookback for more reliable swings on gold
        swing_highs = []
        swing_lows = []
        
        for i in range(3, len(high) - 3):
            if high[i] > high[i-1] and high[i] > high[i+1] and high[i] > high[i-2] and high[i] > high[i+2] and high[i] > high[i-3] and high[i] > high[i+3]:
                swing_highs.append((i, high[i]))
            if low[i] < low[i-1] and low[i] < low[i+1] and low[i] < low[i-2] and low[i] < low[i+2] and low[i] < low[i-3] and low[i] < low[i+3]:
                swing_lows.append((i, low[i]))
        
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return None
        
        score = 0
        direction = SignalDirection.NEUTRAL
        
        # BOS: Break above last swing high (bullish) or below last swing low (bearish)
        last_sh = swing_highs[-1][1]
        last_sl = swing_lows[-1][1]
        
        if current_price > last_sh:
            score = 70
            direction = SignalDirection.BUY
            entry = current_price
            # ponytail: SL at midpoint for better R:R
            sl = (current_price + last_sl) / 2
            tp = current_price + (current_price - sl) * 2.5
        elif current_price < last_sl:
            score = 70
            direction = SignalDirection.SELL
            entry = current_price
            sl = (current_price + last_sh) / 2
            tp = current_price - (sl - current_price) * 2.5
        
        # CHoCH: Previous structure was opposite
        if len(swing_highs) >= 2:
            prev_sh = swing_highs[-2][1]
            if direction == SignalDirection.BUY and last_sh > prev_sh:
                score += 10  # Higher high = trend continuation
            elif direction == SignalDirection.SELL and last_sl < swing_lows[-2][1]:
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
            reasoning=f"BOS {'bullish' if direction == SignalDirection.BUY else 'bearish'}",
            timeframe="M15",
        )

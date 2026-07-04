"""
Strategy 1: Order Block (ICT)
Identifies institutional order blocks on higher timeframes
"""

from typing import Dict, Optional
from .base import GoldStrategy
from ..core.engine import StrategySignal, SignalDirection


class OrderBlockStrategy(GoldStrategy):
    name = "order_block"
    description = "ICT Order Block identification"
    min_timeframe = "H1"
    
    def analyze(self, data: Dict, current_price: float, symbol: str = "XAUUSD") -> Optional[StrategySignal]:
        h1_close = self._get_close(data, "H1")
        h1_high = self._get_high(data, "H1")
        h1_low = self._get_low(data, "H1")
        h4_close = self._get_close(data, "H4")
        
        if len(h1_close) < 50 or len(h4_close) < 20:
            return None
        
        # Find last significant bearish candle before rally (bullish OB)
        # or last significant bullish candle before drop (bearish OB)
        
        score = 0
        direction = SignalDirection.NEUTRAL
        entry = current_price
        sl = current_price
        tp = current_price
        
        # Check for bullish order block
        for i in range(len(h1_close) - 5, max(0, len(h1_close) - 20), -1):
            # Bearish candle followed by bullish move
            if h1_close[i] < h1_close[i-1] and h1_close[i+1] > h1_close[i]:
                ob_top = h1_high[i]
                ob_bottom = h1_low[i]
                
                # Price is near the OB
                if abs(current_price - ob_top) / current_price < 0.002:
                    score = 75
                    direction = SignalDirection.BUY
                    entry = current_price
                    sl = ob_bottom - 5
                    tp = current_price + (current_price - sl) * 2
                    break
        
        # Check for bearish order block
        if score == 0:
            for i in range(len(h1_close) - 5, max(0, len(h1_close) - 20), -1):
                if h1_close[i] > h1_close[i-1] and h1_close[i+1] < h1_close[i]:
                    ob_top = h1_high[i]
                    ob_bottom = h1_low[i]
                    
                    if abs(current_price - ob_bottom) / current_price < 0.002:
                        score = 75
                        direction = SignalDirection.SELL
                        entry = current_price
                        sl = ob_top + 5
                        tp = current_price - (sl - current_price) * 2
                        break
        
        # H4 confirmation
        if len(h4_close) > 5:
            h4_ema = self._calc_ema(h4_close, 20)
            if h4_ema:
                if direction == SignalDirection.BUY and h4_close[-1] > h4_ema[-1]:
                    score += 15
                elif direction == SignalDirection.SELL and h4_close[-1] < h4_ema[-1]:
                    score += 15
        
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
            reasoning=f"Order Block detected on H1, H4 {'confirms' if score > 75 else 'neutral'}",
            timeframe="H1",
        )

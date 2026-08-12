"""
Strategy 3: EMA Cross
EMA 9/21 crossover with trend confirmation
"""

from typing import Dict, Optional
from .base import GoldStrategy
from ..core.engine import StrategySignal, SignalDirection


class EMACrossStrategy(GoldStrategy):
    name = "ema_cross"
    description = "EMA 9/21 crossover"
    min_timeframe = "M15"
    
    def analyze(self, data: Dict, current_price: float, symbol: str = "XAUUSD") -> Optional[StrategySignal]:
        close = self._get_close(data, "M15")
        h4_close = self._get_close(data, "H4")
        
        if len(close) < 30:
            return None
        
        # ponytail: H4 is optional — skip H4 trend if data unavailable
        has_h4 = len(h4_close) >= 30
        
        ema9 = self._calc_ema(close, 9)
        ema21 = self._calc_ema(close, 21)
        ema50 = self._calc_ema(close, 50)
        
        if not ema9 or not ema21:
            return None
        
        score = 0
        direction = SignalDirection.NEUTRAL
        
        # Check for crossover
        if len(ema9) >= 2 and len(ema21) >= 2:
            prev_diff = ema9[-2] - ema21[-2]
            curr_diff = ema9[-1] - ema21[-1]
            
            # Bullish cross
            if prev_diff <= 0 and curr_diff > 0:
                direction = SignalDirection.BUY
                score = 60
                
                # Trend confirmation
                if ema50 and current_price > ema50[-1]:
                    score += 15
                
                # H4 trend (optional)
                if has_h4:
                    h4_ema50 = self._calc_ema(h4_close, 50)
                    if h4_ema50 and h4_close[-1] > h4_ema50[-1]:
                        score += 10
            
            # Bearish cross
            elif prev_diff >= 0 and curr_diff < 0:
                direction = SignalDirection.SELL
                score = 60
                
                if ema50 and current_price < ema50[-1]:
                    score += 15
                
                if has_h4:
                    h4_ema50 = self._calc_ema(h4_close, 50)
                    if h4_ema50 and h4_close[-1] < h4_ema50[-1]:
                        score += 10
        
        if score < 50:
            return None
        
        atr = self._calc_atr(self._get_high(data, "M15"), self._get_low(data, "M15"), close)
        
        if direction == SignalDirection.BUY:
            entry = current_price
            sl = current_price - (atr or 5) * 1.5
            tp = current_price + (atr or 5) * 3.0
        else:
            entry = current_price
            sl = current_price + (atr or 5) * 1.5
            tp = current_price - (atr or 5) * 3.0
        
        return StrategySignal(
            strategy_name=self.name,
            direction=direction,
            confidence=score / 100,
            score=min(score, 100),
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            reasoning=f"EMA 9/21 {'bullish' if direction == SignalDirection.BUY else 'bearish'} cross",
            timeframe="M15",
        )

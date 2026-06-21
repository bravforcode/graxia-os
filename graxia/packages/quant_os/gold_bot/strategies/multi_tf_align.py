"""
Strategy 9: Multi-Timeframe Alignment
All timeframes must agree on direction
"""

from typing import Dict, Optional
from .base import GoldStrategy
from ..core.engine import StrategySignal, SignalDirection


class MultiTFAlignStrategy(GoldStrategy):
    name = "multi_tf_align"
    description = "Multi-timeframe trend alignment"
    
    def analyze(self, data: Dict, current_price: float, symbol: str = "XAUUSD") -> Optional[StrategySignal]:
        tfs = ["M15", "H1", "H4"]
        ema_periods = [20, 50]
        
        alignment = {"BUY": 0, "SELL": 0}
        
        for tf in tfs:
            close = self._get_close(data, tf)
            if len(close) < 50:
                continue
            
            ema20 = self._calc_ema(close, 20)
            ema50 = self._calc_ema(close, 50)
            
            if not ema20 or not ema50:
                continue
            
            if close[-1] > ema20[-1] > ema50[-1]:
                alignment["BUY"] += 1
            elif close[-1] < ema20[-1] < ema50[-1]:
                alignment["SELL"] += 1
        
        score = 0
        direction = SignalDirection.NEUTRAL
        
        # All 3 TFs aligned
        if alignment["BUY"] == 3:
            score = 85
            direction = SignalDirection.BUY
        elif alignment["SELL"] == 3:
            score = 85
            direction = SignalDirection.SELL
        elif alignment["BUY"] == 2:
            score = 75  # ponytail: was 65, too many false signals at 2/3
            direction = SignalDirection.BUY
        elif alignment["SELL"] == 2:
            score = 75
            direction = SignalDirection.SELL
        
        if score < 50:
            return None
        
        close = self._get_close(data, "M15")
        atr = self._calc_atr(self._get_high(data, "M15"), self._get_low(data, "M15"), close)
        
        if direction == SignalDirection.BUY:
            entry = current_price
            sl = current_price - (atr or 5) * 3.0  # ponytail: wider SL for gold M15 noise
            tp = current_price + (atr or 5) * 4.5
        else:
            entry = current_price
            sl = current_price + (atr or 5) * 3.0
            tp = current_price - (atr or 5) * 4.5
        
        return StrategySignal(
            strategy_name=self.name,
            direction=direction,
            confidence=score / 100,
            score=min(score, 100),
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            reasoning=f"Multi-TF alignment: {alignment['BUY']}B/{alignment['SELL']}S",
            timeframe="M15",
        )

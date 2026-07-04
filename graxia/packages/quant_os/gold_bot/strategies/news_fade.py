"""
Strategy 8: News Fade
Fades news-driven moves (mean reversion after news spike)
"""

from typing import Dict, Optional
from .base import GoldStrategy
from ..core.engine import StrategySignal, SignalDirection


class NewsFadeStrategy(GoldStrategy):
    name = "news_fade"
    description = "Fade news-driven spikes"
    
    def analyze(self, data: Dict, current_price: float, symbol: str = "XAUUSD") -> Optional[StrategySignal]:
        close = self._get_close(data, "M1")
        high = self._get_high(data, "M1")
        low = self._get_low(data, "M1")
        
        if len(close) < 30:
            return None
        
        # Detect sudden spike (news event)
        recent_move = abs(close[-1] - close[-10]) / close[-10] * 100
        
        score = 0
        direction = SignalDirection.NEUTRAL
        
        # Large move = potential news spike
        if recent_move > 0.4:  # ponytail: was 0.3, require larger spike for conviction
            # Fade the move
            if close[-1] > close[-10]:
                # Price spiked up, fade short
                score = 60
                direction = SignalDirection.SELL
            else:
                # Price spiked down, fade long
                score = 60
                direction = SignalDirection.BUY
            
            # RSI confirmation (mandatory for entry)
            rsi = self._calc_rsi(close, 14)
            if rsi and direction == SignalDirection.SELL and rsi > 70:
                score += 15
            elif rsi and direction == SignalDirection.BUY and rsi < 30:
                score += 15
            else:
                score = 0  # ponytail: require RSI confirmation
        
        if score < 50:
            return None
        
        atr = self._calc_atr(high, low, close, 14)
        
        if direction == SignalDirection.BUY:
            entry = current_price
            sl = current_price - (atr or 5) * 1.5  # ponytail: tighter SL
            tp = current_price + (atr or 5) * 2.5  # ponytail: wider TP for better R:R
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
            reasoning=f"News fade: {recent_move:.2f}% spike detected",
            timeframe="M1",
        )

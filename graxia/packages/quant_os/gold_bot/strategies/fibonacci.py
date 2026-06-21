"""
Strategy 6: Fibonacci
Fibonacci retracement levels
"""

from typing import Dict, Optional
from .base import GoldStrategy
from ..core.engine import StrategySignal, SignalDirection


class FibonacciStrategy(GoldStrategy):
    name = "fibonacci"
    description = "Fibonacci retracement levels"
    
    def analyze(self, data: Dict, current_price: float, symbol: str = "XAUUSD") -> Optional[StrategySignal]:
        close = self._get_close(data, "H1")
        high = self._get_high(data, "H1")
        low = self._get_low(data, "H1")
        
        if len(close) < 50:
            return None
        
        # Find recent swing high and low (last 50 bars)
        swing_high = max(high[-50:])
        swing_low = min(low[-50:])
        range_size = swing_high - swing_low
        
        if range_size <= 0:
            return None
        
        # Fibonacci levels
        fib_382 = swing_high - range_size * 0.382
        fib_500 = swing_high - range_size * 0.500
        fib_618 = swing_high - range_size * 0.618
        
        score = 0
        direction = SignalDirection.NEUTRAL
        
        # Price near 61.8% retracement (strongest)
        # ponytail: widened proximity from 0.1% to 0.3% for gold volatility
        if abs(current_price - fib_618) / current_price < 0.003:
            score = 75
            # ponytail: fixed direction — BUY if price above fib_618 (bounced), SELL if below
            direction = SignalDirection.BUY if current_price >= fib_618 else SignalDirection.SELL
        # Price near 50% retracement
        elif abs(current_price - fib_500) / current_price < 0.003:
            score = 65
            direction = SignalDirection.BUY if current_price >= fib_500 else SignalDirection.SELL
        # Price near 38.2% retracement
        elif abs(current_price - fib_382) / current_price < 0.003:
            score = 55
            direction = SignalDirection.BUY if current_price >= fib_382 else SignalDirection.SELL
        
        if score < 50:
            return None
        
        if direction == SignalDirection.BUY:
            entry = current_price
            # ponytail: ATR-based SL instead of fixed 5pt
            atr_val = self._calc_atr(high, low, close)
            sl = fib_618 - (atr_val or 8) * 0.5
            tp = fib_500  # target next fib level
        else:
            entry = current_price
            atr_val = self._calc_atr(high, low, close)
            sl = fib_382 + (atr_val or 8) * 0.5
            tp = fib_500  # target next fib level
        
        return StrategySignal(
            strategy_name=self.name,
            direction=direction,
            confidence=score / 100,
            score=min(score, 100),
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            reasoning=f"Fibonacci {'38.2' if score == 55 else '50' if score == 65 else '61.8'}% level",
            timeframe="H1",
        )

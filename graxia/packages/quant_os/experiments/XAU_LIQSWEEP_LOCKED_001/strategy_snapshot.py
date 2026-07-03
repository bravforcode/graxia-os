"""
Strategy 11: Liquidity Sweep ✦
Liquidity grab above/below key levels
"""

from ..core.engine import SignalDirection, StrategySignal
from .base import GoldStrategy


class LiquiditySweepStrategy(GoldStrategy):
    name = "liquidity_sweep"
    description = "Liquidity sweep detection"

    def analyze(self, data: dict, current_price: float, symbol: str = "XAUUSD") -> StrategySignal | None:
        high = self._get_high(data, "M15")
        low = self._get_low(data, "M15")
        close = self._get_close(data, "M15")

        if len(close) < 30:
            return None

        # ponytail: ATR-based SL buffer for symbol adaptivity
        atr_val = self._calc_atr(high, low, close) or 5.0
        sl_buffer = atr_val * 0.5  # 0.5x ATR buffer

        score = 0
        direction = SignalDirection.NEUTRAL

        # Find equal highs/lows (liquidity pools)
        for i in range(len(high) - 5, max(0, len(high) - 20), -1):
            for j in range(i - 1, max(0, i - 5), -1):
                if j >= len(high) or i >= len(high):
                    continue

                # Equal highs (buy-side liquidity)
                if abs(high[i] - high[j]) / high[i] < 0.0005:
                    # Price swept above and came back
                    sweep_high = max(high[min(i, j) : max(i, j) + 1])
                    if sweep_high > high[i] and close[-1] < high[i]:
                        score = 80
                        direction = SignalDirection.SELL
                        entry = current_price
                        sl = sweep_high + sl_buffer  # ATR-based buffer
                        tp = current_price - (sl - current_price) * 2.5  # 2.5x R:R
                        break

                # Equal lows (sell-side liquidity)
                if abs(low[i] - low[j]) / low[i] < 0.0005:
                    sweep_low = low[min(i, j) : max(i, j) + 1]
                    if sweep_low and min(sweep_low) < low[i] and close[-1] > low[i]:
                        score = 80
                        direction = SignalDirection.BUY
                        entry = current_price
                        sl = min(sweep_low) - sl_buffer  # ATR-based buffer
                        tp = current_price + (current_price - sl) * 2.5  # 2.5x R:R
                        break

            if score > 0:
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
            reasoning=f"Liquidity sweep {'above highs' if direction == SignalDirection.SELL else 'below lows'}",
            timeframe="M15",
        )

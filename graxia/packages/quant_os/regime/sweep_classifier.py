"""Sweep Classifier — detects liquidity sweeps and classifies as reversal/continuation.

Input: OHLCV bars + liquidity levels + regime result.
Output: SweepSignal (REVERSAL | CONTINUATION | NO_TRADE) with confidence.
"""
from dataclasses import dataclass
from typing import List, Optional
from .liquidity_map import LiquidityLevel


@dataclass
class SweepSignal:
    signal: str  # REVERSAL | CONTINUATION | NO_TRADE
    side: str  # BUY | SELL (only for REVERSAL/CONTINUATION)
    level_id: str = ""
    confidence: float = 0.0  # 0.0–1.0
    quality_score: float = 0.0  # 0.0–1.0 (how clean is the setup)
    reclaim_score: float = 0.0  # 0.0–1.0 (reclaim strength)
    directional_context: str = ""  # BULLISH | BEARISH
    invalidation_price: float = 0.0
    reason_code: str = ""
    sweep_price: float = 0.0
    reclaim_bars: int = 0


class SweepClassifier:
    """Classify liquidity sweeps as reversal, continuation, or no-trade.

    Args:
        bars: OHLCV data with keys: time, open, high, low, close, volume
        levels: LiquidityLevels from LiquidityMap
        regime: TREND_UP | TREND_DOWN | RANGE | UNCLEAR
        spread_state: NORMAL | SPIKE
    """

    # Thresholds
    MIN_WICK_BODY_RATIO = 2.0  # wick must be 2x body
    MAX_RECLAIM_BARS = 3  # must reclaim within this many bars
    MIN_SWEEP_ATR = 0.3  # sweep must be at least 0.3x ATR
    QUALITY_HIGH = 0.7
    QUALITY_LOW = 0.3

    def __init__(self, bars: List[dict], levels: List[LiquidityLevel],
                 regime: str = "UNCLEAR", spread_state: str = "NORMAL"):
        self.bars = bars
        self.levels = levels
        self.regime = regime
        self.spread_state = spread_state
        self._atr = self._calc_atr(14)

    def classify(self) -> List[SweepSignal]:
        """Classify the most recent sweep setups."""
        if len(self.bars) < 10 or not self.levels:
            return []

        signals = []

        for level in self.levels:
            signal = self._check_level(level)
            if signal:
                signals.append(signal)

        # Return sorted by confidence, only top signals
        signals.sort(key=lambda x: x.confidence, reverse=True)
        return signals[:5]

    def _check_level(self, level: LiquidityLevel) -> Optional[SweepSignal]:
        """Check if a single liquidity level was swept and classify."""
        # Only check recent bars (last 10)
        lookback = min(10, len(self.bars))
        recent = self.bars[-lookback:]

        atr = self._atr if self._atr > 0 else 0.001
        level_price = level.price
        min_sweep = atr * self.MIN_SWEEP_ATR

        # Find sweep events
        for i, bar in enumerate(recent):
            close = bar["close"]
            high = bar["high"]
            low = bar["low"]

            # Check if this bar swept THROUGH the level
            above_level = high > level_price + min_sweep
            below_level = low < level_price - min_sweep
            
            if not above_level and not below_level:
                continue

            # Determine sweep direction — use wick depth when both sides swept
            if above_level and not below_level:
                sweep_side = "SELL"
            elif below_level and not above_level:
                sweep_side = "BUY"
            else:
                # Both sides swept: deeper wick determines true sweep direction
                wick_above = high - level_price
                wick_below = level_price - low
                if close >= level_price:
                    sweep_side = "BUY" if wick_below > wick_above else "SELL"
                else:
                    sweep_side = "SELL" if wick_above > wick_below else "BUY"

            # Analyze the sweep bar
            body = abs(close - bar["open"])
            upper_wick = high - max(close, bar["open"])
            lower_wick = min(close, bar["open"]) - low
            wick = upper_wick if sweep_side == "SELL" else lower_wick
            wick_body_ratio = wick / body if body > 0 else 99

            # Reclaim check: did price close back inside the swept level?
            reclaimed = False
            reclaim_bars = 99
            remaining = recent[i:]
            for j, rbar in enumerate(remaining):
                if sweep_side == "BUY" and rbar["close"] > level_price:
                    reclaimed = True
                    reclaim_bars = j
                    break
                if sweep_side == "SELL" and rbar["close"] < level_price:
                    reclaimed = True
                    reclaim_bars = j
                    break

            # Scores
            wick_score = min(1.0, wick_body_ratio / self.MIN_WICK_BODY_RATIO)
            reclaim_score = 1.0 - (reclaim_bars / self.MAX_RECLAIM_BARS) if reclaimed else 0.0
            quality = (wick_score + reclaim_score) / 2

            # Directional context from sweep side
            directional = "BULLISH" if sweep_side == "BUY" else "BEARISH"

            # Determine signal type
            if not reclaimed and reclaim_bars > self.MAX_RECLAIM_BARS:
                # Swept and no reclaim → potential continuation
                if self.regime in ("TREND_UP", "TREND_DOWN"):
                    # Continuation in trend direction
                    if (sweep_side == "BUY" and self.regime == "TREND_DOWN") or \
                       (sweep_side == "SELL" and self.regime == "TREND_UP"):
                        signal = "CONTINUATION"
                        side = sweep_side
                        invalidation = level_price * 1.02 if side == "BUY" else level_price * 0.98
                    else:
                        # Sweep against trend → skip
                        signal = "NO_TRADE"
                        side = ""
                        invalidation = 0
                else:
                    signal = "NO_TRADE"
                    side = ""
                    invalidation = 0

            elif reclaimed and reclaim_score >= 0.25:
                # Reclaimed → reversal candidate
                if self.spread_state == "SPIKE":
                    signal = "NO_TRADE"
                    side = ""
                    invalidation = 0
                elif quality >= self.QUALITY_LOW:
                    signal = "REVERSAL"
                    side = sweep_side
                    invalidation = high if sweep_side == "SELL" else low
                else:
                    signal = "NO_TRADE"
                    side = ""
                    invalidation = 0
            else:
                signal = "NO_TRADE"
                side = ""
                invalidation = 0

            if signal == "NO_TRADE" or self.regime == "UNCLEAR":
                continue

            # Final confidence
            base_conf = quality
            if self.regime == "RANGE" and signal == "REVERSAL":
                base_conf += 0.15  # reversal favored in range
            if self.regime in ("TREND_UP", "TREND_DOWN") and signal == "CONTINUATION":
                base_conf += 0.2  # continuation favored in trend
            if self.regime == "UNCLEAR":
                base_conf -= 0.2

            return SweepSignal(
                signal=signal, side=side,
                level_id=level.reason_code,
                confidence=round(min(1.0, base_conf), 3),
                quality_score=round(quality, 3),
                reclaim_score=round(reclaim_score, 3),
                directional_context=directional,
                invalidation_price=round(invalidation, 5),
                reason_code=f"{signal}_{side}_wk={wick_body_ratio:.1f}_rc={reclaim_bars}",
                sweep_price=round(level_price, 5),
                reclaim_bars=reclaim_bars,
            )

        return None

    def _calc_atr(self, period: int = 14) -> float:
        """Calculate ATR from bars."""
        if len(self.bars) < period:
            return 0.0
        trs = []
        for i in range(1, len(self.bars)):
            hl = self.bars[i]["high"] - self.bars[i]["low"]
            hc = abs(self.bars[i]["high"] - self.bars[i - 1]["close"])
            lc = abs(self.bars[i]["low"] - self.bars[i - 1]["close"])
            trs.append(max(hl, hc, lc))
        if not trs:
            return 0.0
        return sum(trs[-period:]) / min(period, len(trs))

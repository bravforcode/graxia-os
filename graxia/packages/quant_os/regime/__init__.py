"""Regime Detector — determines market regime from OHLCV data.

Output: TREND_UP, TREND_DOWN, RANGE, or UNCLEAR with confidence score.
"""
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class RegimeResult:
    regime: str  # TREND_UP | TREND_DOWN | RANGE | UNCLEAR
    confidence: float  # 0.0–1.0
    adx_value: float
    ema_slope: float
    atr_state: str  # EXPANDING | CONTRACTING | NORMAL
    spread_state: str  # NORMAL | SPIKE
    reason_code: str  # debug summary


class RegimeDetector:
    """Rule-based market regime detector.

    Indicators: ADX(14), EMA50 slope, ATR(14) regime, spread regime.
    Timeframe: M15 (300 bars default).
    """

    # Thresholds
    ADX_TREND_MIN = 22
    ADX_STRONG = 35
    ADX_RANGE_MAX = 20
    EMA_SLOPE_TREND = 0.00015  # normalized slope threshold
    ATR_EXPAND_RATIO = 1.3  # ATR / SMA(ATR) above this = expanding
    ATR_CONTRACT_RATIO = 0.7  # below this = contracting
    SPREAD_SPIKE_RATIO = 2.5  # current spread / avg spread above this = spike

    def __init__(self):
        pass

    def detect(self, closes: List[float], highs: List[float], lows: List[float],
               spreads: Optional[List[float]] = None) -> RegimeResult:
        """Detect regime from OHLCV data.
        
        Args:
            closes: Close prices (need >= 50 bars)
            highs: High prices
            lows: Low prices
            spreads: Optional bid/ask spread data
        
        Returns:
            RegimeResult with regime classification and confidence
        """
        if len(closes) < 50:
            return RegimeResult("UNCLEAR", 0.0, 0, 0, "NORMAL", "NORMAL",
                                "insufficient data")

        # --- ADX(14) ---
        adx = self._calc_adx(highs, lows, closes, 14)

        # --- EMA50 slope ---
        ema50 = self._calc_ema(closes, 50)
        ema_slope = self._calc_slope(ema50, 5)

        # --- ATR regime ---
        atr = self._calc_atr(highs, lows, closes, 14)
        atr_sma = self._calc_sma(atr, 50) if len(atr) >= 50 else sum(atr) / len(atr)
        atr_current = atr[-1]
        atr_ratio = atr_current / atr_sma if atr_sma > 0 else 1.0
        if atr_ratio > self.ATR_EXPAND_RATIO:
            atr_state = "EXPANDING"
        elif atr_ratio < self.ATR_CONTRACT_RATIO:
            atr_state = "CONTRACTING"
        else:
            atr_state = "NORMAL"

        # --- Spread regime ---
        spread_state = "NORMAL"
        if spreads and len(spreads) >= 20:
            avg_spread = sum(spreads) / len(spreads)
            if avg_spread > 0 and spreads[-1] > avg_spread * self.SPREAD_SPIKE_RATIO:
                spread_state = "SPIKE"

        # --- Decision logic ---
        adx_current = adx[-1]
        reasons = []
        codes = []
        votes = {"trend": 0, "range": 0, "unclear": 0}

        # Vote: ADX
        if adx_current >= self.ADX_TREND_MIN:
            votes["trend"] += 2
            codes.append(f"ADX_HIGH({adx_current:.0f})")
        elif adx_current <= self.ADX_RANGE_MAX:
            votes["range"] += 2
            codes.append(f"ADX_LOW({adx_current:.0f})")
        else:
            votes["unclear"] += 1
            codes.append(f"ADX_MID({adx_current:.0f})")

        # Vote: EMA slope
        if ema_slope > self.EMA_SLOPE_TREND:
            votes["trend"] += 2
            codes.append("SLOPE_UP")
        elif ema_slope < -self.EMA_SLOPE_TREND:
            votes["trend"] += 2
            codes.append("SLOPE_DOWN")
        else:
            votes["range"] += 2
            codes.append("SLOPE_FLAT")

        # Vote: ATR state
        if atr_state == "EXPANDING" and votes["trend"] > 0:
            votes["trend"] += 1
            codes.append("ATR_EXPAND")
        elif atr_state == "CONTRACTING":
            votes["range"] += 1
            codes.append("ATR_CONTRACT")
        else:
            codes.append("ATR_NORMAL")

        # Spread spike override
        if spread_state == "SPIKE":
            return RegimeResult("UNCLEAR", 0.6, adx_current,
                                round(ema_slope, 8), atr_state, spread_state,
                                "SPREAD_SPIKE")

        # Determine regime
        total = votes["trend"] + votes["range"] + votes["unclear"]
        trend_pct = votes["trend"] / total if total > 0 else 0
        range_pct = votes["range"] / total if total > 0 else 0
        unclear_pct = votes["unclear"] / total if total > 0 else 0

        confidence = max(trend_pct, range_pct, unclear_pct)

        # Trend direction from EMA slope
        if trend_pct > range_pct and trend_pct > unclear_pct:
            regime = "TREND_UP" if ema_slope > 0 else "TREND_DOWN"
        elif range_pct > trend_pct and range_pct > unclear_pct:
            regime = "RANGE"
        else:
            regime = "UNCLEAR"

        reason = " | ".join(codes)
        return RegimeResult(regime, round(confidence, 3), adx_current,
                            round(ema_slope, 8), atr_state, spread_state, reason)

    # --- Internal helpers ---

    def _calc_adx(self, highs: List[float], lows: List[float],
                  closes: List[float], period: int) -> List[float]:
        """Wilder's ADX"""
        tr = []
        for i in range(1, len(closes)):
            hl = highs[i] - lows[i]
            hc = abs(highs[i] - closes[i - 1])
            lc = abs(lows[i] - closes[i - 1])
            tr.append(max(hl, hc, lc))

        # Directional movement
        up = []
        down = []
        for i in range(1, len(closes)):
            up_move = highs[i] - highs[i - 1]
            down_move = lows[i - 1] - lows[i]
            up.append(up_move if up_move > down_move and up_move > 0 else 0)
            down.append(down_move if down_move > up_move and down_move > 0 else 0)

        # Smoothed ATR, +DI, -DI
        atr_vals = self._wilder_smooth(tr, period)
        up_smooth = self._wilder_smooth(up, period)
        down_smooth = self._wilder_smooth(down, period)

        # +DI, -DI, DX
        di_len = min(len(atr_vals), len(up_smooth), len(down_smooth))
        dx = []
        for i in range(di_len):
            if atr_vals[i] > 0:
                pdi = 100 * up_smooth[i] / atr_vals[i]
                ndi = 100 * down_smooth[i] / atr_vals[i]
                diff = abs(pdi - ndi)
                summ = pdi + ndi
                dx.append(100 * diff / summ if summ > 0 else 0)
            else:
                dx.append(0)

        return self._wilder_smooth(dx, period)

    def _wilder_smooth(self, values: List[float], period: int) -> List[float]:
        """Wilder's smoothing (modified EMA)"""
        if not values or period <= 1:
            return []
        smooth = [sum(values[:period]) / period]
        for v in values[period:]:
            smooth.append((smooth[-1] * (period - 1) + v) / period)
        return smooth

    def _calc_ema(self, values: List[float], period: int) -> List[float]:
        """Exponential Moving Average"""
        if len(values) < period:
            return []
        multiplier = 2 / (period + 1)
        ema = [sum(values[:period]) / period]
        for v in values[period:]:
            ema.append((v - ema[-1]) * multiplier + ema[-1])
        return ema

    def _calc_sma(self, values: List[float], period: int) -> float:
        """Simple Moving Average of last N values"""
        if len(values) < period:
            return sum(values) / len(values)
        return sum(values[-period:]) / period

    def _calc_slope(self, values: List[float], lookback: int) -> float:
        """Normalized slope: (last - first) / first over lookback bars"""
        if len(values) < lookback + 1:
            return 0.0
        recent = values[-(lookback + 1):]
        return (recent[-1] - recent[0]) / recent[0] if recent[0] != 0 else 0.0

    def _calc_atr(self, highs: List[float], lows: List[float],
                  closes: List[float], period: int) -> List[float]:
        """Average True Range"""
        tr = []
        for i in range(1, len(closes)):
            hl = highs[i] - lows[i]
            hc = abs(highs[i] - closes[i - 1])
            lc = abs(lows[i] - closes[i - 1])
            tr.append(max(hl, hc, lc))
        return self._wilder_smooth(tr, period)

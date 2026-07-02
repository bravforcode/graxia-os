"""
Regime Filter — Detect market conditions

Classifies market into regimes:
- TRENDING_UP / TRENDING_DOWN
- RANGING
- HIGH_VOLATILITY
- LOW_VOLATILITY
- CRISIS

Used to:
- Enable/disable strategies based on regime
- Adjust position sizing
- Filter false signals
"""

import math
from dataclasses import dataclass
from enum import Enum


class MarketRegime(str, Enum):
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    CRISIS = "CRISIS"


@dataclass
class RegimeResult:
    """Regime detection result"""

    regime: MarketRegime
    confidence: float  # 0.0 - 1.0
    adx: float = 0.0
    plus_di: float = 0.0
    minus_di: float = 0.0
    volatility: float = 0.0
    trend_strength: float = 0.0
    details: dict = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}


class RegimeFilter:
    """
    Detects market regime using multiple indicators.

    Logic:
    1. ADX for trend strength
    2. ATR for volatility
    3. EMA alignment for direction
    4. Bollinger Band width for volatility regime
    """

    def __init__(
        self,
        adx_period: int = 14,
        adx_trend_threshold: float = 25.0,
        adx_strong_threshold: float = 40.0,
        vol_lookback: int = 20,
        vol_high_mult: float = 1.5,
        vol_low_mult: float = 0.5,
    ):
        self.adx_period = adx_period
        self.adx_trend_threshold = adx_trend_threshold
        self.adx_strong_threshold = adx_strong_threshold
        self.vol_lookback = vol_lookback
        self.vol_high_mult = vol_high_mult
        self.vol_low_mult = vol_low_mult

    def detect(self, data: dict[str, list[float]]) -> RegimeResult:
        """
        Detect current market regime.

        Args:
            data: Dict with 'open', 'high', 'low', 'close', 'volume'

        Returns:
            RegimeResult with detected regime
        """
        close = data.get("close", [])
        high = data.get("high", [])
        low = data.get("low", [])

        if len(close) < 50:
            return RegimeResult(
                regime=MarketRegime.RANGING,
                confidence=0.3,
                details={"reason": "insufficient_data"},
            )

        # Calculate indicators
        adx, plus_di, minus_di = self._calc_adx(high, low, close, self.adx_period)
        volatility = self._calc_volatility(close, self.vol_lookback)
        avg_volatility = self._calc_avg_volatility(close, self.vol_lookback)
        trend_direction = self._calc_trend_direction(close)
        bb_width = self._calc_bb_width(close, 20)

        # Determine regime
        regime, confidence = self._classify_regime(adx, volatility, avg_volatility, trend_direction, bb_width)

        return RegimeResult(
            regime=regime,
            confidence=confidence,
            adx=adx,
            plus_di=plus_di,
            minus_di=minus_di,
            volatility=volatility,
            trend_strength=adx / 100,
            details={
                "avg_volatility": avg_volatility,
                "trend_direction": trend_direction,
                "bb_width": bb_width,
            },
        )

    def _calc_adx(
        self, high: list[float], low: list[float], close: list[float], period: int
    ) -> tuple[float, float, float]:
        """Calculate Average Directional Index (Wilder's smoothed).

        Returns (adx, plus_di, minus_di).
        """
        if len(close) < period + 1:
            return 0.0, 0.0, 0.0

        trs = []
        plus_dm = []
        minus_dm = []

        for i in range(1, len(close)):
            h_l = high[i] - low[i]
            h_pc = abs(high[i] - close[i - 1])
            l_pc = abs(low[i] - close[i - 1])
            tr = max(h_l, h_pc, l_pc)
            trs.append(tr)

            up = high[i] - high[i - 1]
            down = low[i - 1] - low[i]

            plus_dm.append(up if up > down and up > 0 else 0)
            minus_dm.append(down if down > up and down > 0 else 0)

        if len(trs) < period:
            return 0.0, 0.0, 0.0

        atr = sum(trs[:period]) / period
        smooth_plus = sum(plus_dm[:period]) / period
        smooth_minus = sum(minus_dm[:period]) / period

        dx_values = []
        for i in range(period, len(trs)):
            atr = (atr * (period - 1) + trs[i]) / period
            smooth_plus = (smooth_plus * (period - 1) + plus_dm[i]) / period
            smooth_minus = (smooth_minus * (period - 1) + minus_dm[i]) / period

            if atr == 0:
                dx_values.append(0.0)
                continue
            pdi = (smooth_plus / atr) * 100
            mdi = (smooth_minus / atr) * 100
            di_sum = pdi + mdi
            dx_values.append(abs(pdi - mdi) / di_sum * 100 if di_sum != 0 else 0.0)

        # Wilder's smoothing of DX → true ADX
        if not dx_values:
            return 0.0, 0.0, 0.0
        adx = sum(dx_values[:period]) / period
        for dx in dx_values[period:]:
            adx = (adx * (period - 1) + dx) / period

        # Final DI values for reporting
        if atr == 0:
            return adx, 0.0, 0.0
        final_pdi = (smooth_plus / atr) * 100
        final_mdi = (smooth_minus / atr) * 100

        return adx, final_pdi, final_mdi

    def _calc_volatility(self, close: list[float], period: int) -> float:
        """Calculate current volatility (normalized ATR)"""
        if len(close) < period + 1:
            return 0.0

        returns = [(close[i] - close[i - 1]) / close[i - 1] for i in range(1, len(close))]
        recent = returns[-period:]

        if not recent:
            return 0.0

        mean = sum(recent) / len(recent)
        variance = sum((r - mean) ** 2 for r in recent) / len(recent)

        return math.sqrt(variance) * 100

    def _calc_avg_volatility(self, close: list[float], period: int) -> float:
        """Calculate average volatility over longer period"""
        if len(close) < period * 3:
            return self._calc_volatility(close, period)

        volatilities = []
        for i in range(period * 3, len(close), period):
            vol = self._calc_volatility(close[:i], period)
            volatilities.append(vol)

        return sum(volatilities) / len(volatilities) if volatilities else 0.0

    def _calc_trend_direction(self, close: list[float]) -> float:
        """Calculate trend direction using EMA alignment"""
        if len(close) < 50:
            return 0.0

        ema20 = self._ema(close, 20)
        ema50 = self._ema(close, 50)

        if not ema20 or not ema50:
            return 0.0

        # Positive = bullish, negative = bearish
        diff = (ema20[-1] - ema50[-1]) / ema50[-1] * 100

        return max(-1, min(1, diff))

    def _calc_bb_width(self, close: list[float], period: int) -> float:
        """Calculate Bollinger Band width"""
        if len(close) < period:
            return 0.0

        recent = close[-period:]
        mean = sum(recent) / len(recent)
        variance = sum((x - mean) ** 2 for x in recent) / len(recent)
        std = math.sqrt(variance)

        return (std * 2 / mean) * 100 if mean > 0 else 0.0

    def _ema(self, data: list[float], period: int) -> list[float]:
        """Calculate EMA"""
        if len(data) < period:
            return []

        multiplier = 2 / (period + 1)
        ema = [sum(data[:period]) / period]

        for price in data[period:]:
            ema.append((price - ema[-1]) * multiplier + ema[-1])

        return ema

    def _classify_regime(
        self,
        adx: float,
        volatility: float,
        avg_volatility: float,
        trend_direction: float,
        bb_width: float,
    ) -> tuple[MarketRegime, float]:
        """Classify market regime based on indicators"""

        if avg_volatility == 0:
            return MarketRegime.RANGING, 0.3

        # Crisis detection (extreme volatility)
        if volatility > avg_volatility * 3 and bb_width > 4.0:
            return MarketRegime.CRISIS, 0.9

        # High volatility
        if volatility > avg_volatility * self.vol_high_mult:
            return MarketRegime.HIGH_VOLATILITY, min(0.9, volatility / (avg_volatility * 2))

        # Low volatility
        if volatility < avg_volatility * self.vol_low_mult:
            return MarketRegime.LOW_VOLATILITY, min(0.9, 1 - volatility / avg_volatility)

        # Trending
        if adx > self.adx_strong_threshold:
            if trend_direction > 0:
                return MarketRegime.TRENDING_UP, min(0.95, 0.7 + adx / 200)
            else:
                return MarketRegime.TRENDING_DOWN, min(0.95, 0.7 + adx / 200)

        if adx > self.adx_trend_threshold:
            if trend_direction > 0.1:
                return MarketRegime.TRENDING_UP, 0.6 + adx / 200
            elif trend_direction < -0.1:
                return MarketRegime.TRENDING_DOWN, 0.6 + adx / 200

        # Ranging
        return MarketRegime.RANGING, max(0.3, 1 - adx / 50)

    def get_position_multiplier(self, regime: MarketRegime, confidence: float = 1.0) -> float:
        """Return position size multiplier based on regime + confidence.

        Used by risk engine to reduce exposure during dangerous regimes.
        CRISIS → 0.0 (no trading)
        HIGH_VOLATILITY → 0.25 (cut 75%)
        LOW_VOLATILITY → 0.75
        Others → 1.0 scaled by confidence
        """
        base = {
            MarketRegime.CRISIS: 0.0,
            MarketRegime.HIGH_VOLATILITY: 0.25,
            MarketRegime.LOW_VOLATILITY: 0.75,
            MarketRegime.TRENDING_UP: 1.0,
            MarketRegime.TRENDING_DOWN: 1.0,
            MarketRegime.RANGING: 0.8,
        }.get(regime, 0.5)
        # Scale by confidence: low confidence → reduce position further
        return base * (0.5 + 0.5 * confidence)

    def detect_regime_shift_risk(self, close: list[float], lookback: int = 50) -> dict:
        """Detect accelerating volatility shift — early warning for regime change.

        The stress test shows regime_shift scenario causes -155% PnL and 631% DD.
        This method detects the precursor: volatility accelerating faster than normal.

        Returns dict with risk_score (0-1), warning, and metrics.
        """
        if len(close) < lookback * 2:
            return {"risk_score": 0.0, "warning": False, "reason": "insufficient_data"}

        recent = close[-lookback:]
        older = close[-lookback * 2 : -lookback]

        recent_vol = self._calc_volatility(recent, min(10, len(recent) // 5))
        older_vol = self._calc_volatility(older, min(10, len(older) // 5))

        if older_vol == 0:
            return {"risk_score": 0.0, "warning": False}

        vol_ratio = recent_vol / older_vol
        # If volatility doubles → high risk
        risk_score = min(1.0, max(0.0, (vol_ratio - 1.0) / 3.0))
        warning = risk_score > 0.5  # >2x vol increase

        return {
            "risk_score": risk_score,
            "warning": warning,
            "vol_ratio": vol_ratio,
            "recent_vol": recent_vol,
            "older_vol": older_vol,
        }

    def get_allowed_strategies(self, regime: MarketRegime) -> list[str]:
        """Get strategies allowed for current regime"""
        regime_strategies = {
            MarketRegime.TRENDING_UP: [
                "ema_cross",
                "multi_tf_align",
                "bos_choch",
                "order_block",
                "liquidity_sweep",
                "opening_range",
            ],
            MarketRegime.TRENDING_DOWN: [
                "ema_cross",
                "multi_tf_align",
                "bos_choch",
                "order_block",
                "liquidity_sweep",
                "opening_range",
            ],
            MarketRegime.RANGING: [
                "supply_demand",
                "fibonacci",
                "vwap_rejection",
                "fair_value_gap",
                "rsi_divergence",
            ],
            MarketRegime.HIGH_VOLATILITY: [
                "news_fade",
                "liquidity_sweep",
                "fair_value_gap",
            ],
            MarketRegime.LOW_VOLATILITY: [
                "london_breakout",
                "opening_range",
                "supply_demand",
            ],
            MarketRegime.CRISIS: [],  # No trading in crisis
        }

        return regime_strategies.get(regime, [])

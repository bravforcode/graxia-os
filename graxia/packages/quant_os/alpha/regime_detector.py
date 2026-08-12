"""
Regime Detector — per-asset-class market regime classification.

Detects regimes using asset-class-specific methods:
- metals:  ADX-based (TRENDING_UP, TRENDING_DOWN, RANGING, HIGH_VOLATILITY,
           LOW_VOLATILITY, CRISIS)
- crypto:  Volatility clustering (BULL, BEAR, ACCUMULATION, DISTRIBUTION,
           EXTREME_VOLATILITY)
- forex:   ADX-based (TRENDING, RANGING, NEWS_DRIVEN, LOW_LIQUIDITY)
- indices: VIX-based (RISK_ON, RISK_OFF, EARNINGS, LOW_VOL, CRASH)

Each regime maps to a position multiplier and a list of allowed strategies.
"""

from __future__ import annotations

from typing import Any, Dict, List

import structlog

from ..core.signal_gateway import AssetClass

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Regime labels per asset class
# ---------------------------------------------------------------------------

METALS_REGIMES = {
    "TRENDING_UP",
    "TRENDING_DOWN",
    "RANGING",
    "HIGH_VOLATILITY",
    "LOW_VOLATILITY",
    "CRISIS",
}

CRYPTO_REGIMES = {
    "BULL",
    "BEAR",
    "ACCUMULATION",
    "DISTRIBUTION",
    "EXTREME_VOLATILITY",
}

FOREX_REGIMES = {
    "TRENDING",
    "RANGING",
    "NEWS_DRIVEN",
    "LOW_LIQUIDITY",
}

INDICES_REGIMES = {
    "RISK_ON",
    "RISK_OFF",
    "EARNINGS",
    "LOW_VOL",
    "CRASH",
}


# ---------------------------------------------------------------------------
# Position multipliers by regime
# ---------------------------------------------------------------------------

_POSITION_MULTIPLIERS: Dict[str, float] = {
    # Metals
    "TRENDING_UP": 1.0,
    "TRENDING_DOWN": 0.8,
    "RANGING": 0.6,
    "HIGH_VOLATILITY": 0.5,
    "LOW_VOLATILITY": 0.8,
    "CRISIS": 0.2,
    # Crypto
    "BULL": 1.0,
    "BEAR": 0.5,
    "ACCUMULATION": 0.7,
    "DISTRIBUTION": 0.4,
    "EXTREME_VOLATILITY": 0.3,
    # Forex
    "TRENDING": 1.0,
    "RANGING": 0.7,
    "NEWS_DRIVEN": 0.3,
    "LOW_LIQUIDITY": 0.4,
    # Indices
    "RISK_ON": 1.0,
    "RISK_OFF": 0.5,
    "EARNINGS": 0.4,
    "LOW_VOL": 0.9,
    "CRASH": 0.1,
}


# ---------------------------------------------------------------------------
# Allowed strategies by regime
# ---------------------------------------------------------------------------

_ALLOWED_STRATEGIES: Dict[str, Dict[str, List[str]]] = {
    "metals": {
        "TRENDING_UP": ["mtm", "mlb", "ensemble"],
        "TRENDING_DOWN": ["mtm", "mlb", "ensemble"],
        "RANGING": ["mrb", "ensemble"],
        "HIGH_VOLATILITY": ["mlb", "ensemble"],
        "LOW_VOLATILITY": ["mrb", "mtm", "ensemble"],
        "CRISIS": [],  # no trading in crisis
    },
    "crypto": {
        "BULL": ["momentum", "breakout"],
        "BEAR": ["mean_reversion", "breakout"],
        "ACCUMULATION": ["accumulation", "dca"],
        "DISTRIBUTION": ["mean_reversion"],
        "EXTREME_VOLATILITY": [],  # abstain
    },
    "forex": {
        "TRENDING": ["mtm", "mlb", "ensemble"],
        "RANGING": ["mrb", "ensemble"],
        "NEWS_DRIVEN": [],  # abstain during news
        "LOW_LIQUIDITY": [],  # abstain
    },
    "indices": {
        "RISK_ON": ["mtm", "mlb", "ensemble"],
        "RISK_OFF": ["mean_reversion"],
        "EARNINGS": [],  # abstain during earnings
        "LOW_VOL": ["mrb", "mtm", "ensemble"],
        "CRASH": [],  # abstain
    },
}


# ---------------------------------------------------------------------------
# Regime Detector
# ---------------------------------------------------------------------------


class RegimeDetector:
    """Per-asset-class market regime detector.

    Uses different detection methods per asset class:
    - metals/forex: ADX(14) + EMA slope + ATR state
    - crypto: volatility clustering + returns distribution
    - indices: VIX proxy + breadth + ATR state
    """

    # ADX thresholds (shared by metals and forex)
    ADX_TREND_MIN: float = 22.0
    ADX_STRONG: float = 35.0
    ADX_RANGE_MAX: float = 20.0

    # Volatility thresholds
    ATR_EXPAND_RATIO: float = 1.3
    ATR_CONTRACT_RATIO: float = 0.7

    # Crypto volatility cluster threshold
    CRYPTO_VOL_HIGH_PERCENTILE: float = 90.0
    CRYPTO_VOL_LOW_PERCENTILE: float = 10.0

    def detect(self, data: Dict[str, Any], asset_class: AssetClass) -> str:
        """Detect current regime for the given asset class.

        Args:
            data: Market data dict. Expected keys vary by asset class:
                  - metals/forex: closes, highs, lows (lists of floats)
                  - crypto: closes, volumes (lists of floats)
                  - indices: closes, vix_proxy (list of floats)
            asset_class: The asset class to detect regime for.

        Returns:
            Regime label string.
        """
        if asset_class == AssetClass.METALS:
            return self._detect_metals(data)
        if asset_class == AssetClass.CRYPTO:
            return self._detect_crypto(data)
        if asset_class == AssetClass.FOREX:
            return self._detect_forex(data)
        if asset_class == AssetClass.INDICES:
            return self._detect_indices(data)
        return "UNKNOWN"

    def get_position_multiplier(self, regime: str) -> float:
        """Return position size multiplier for a given regime.

        Args:
            regime: Regime label string.

        Returns:
            Float multiplier (0.0–1.0). 0.0 means no trading.
        """
        return _POSITION_MULTIPLIERS.get(regime, 0.5)

    def get_allowed_strategies(self, regime: str, asset_class: AssetClass) -> List[str]:
        """Return list of strategy names allowed in the given regime.

        Args:
            regime: Regime label string.
            asset_class: The asset class.

        Returns:
            List of allowed strategy name strings. Empty list = abstain.
        """
        class_strategies = _ALLOWED_STRATEGIES.get(asset_class.value, {})
        return class_strategies.get(regime, [])

    # ------------------------------------------------------------------
    # Metals detection (ADX-based)
    # ------------------------------------------------------------------

    def _detect_metals(self, data: Dict[str, Any]) -> str:
        """Detect metals regime using ADX, EMA slope, and ATR state."""
        closes = self._extract_series(data, "closes", "close")
        highs = self._extract_series(data, "highs", "high")
        lows = self._extract_series(data, "lows", "low")

        if len(closes) < 50:
            return "RANGING"  # default for insufficient data

        adx = self._calc_adx(highs, lows, closes, 14)
        adx_val = adx[-1] if adx else 0.0

        ema50 = self._calc_ema(closes, 50)
        ema_slope = self._calc_slope(ema50, 5)

        atr = self._calc_atr(highs, lows, closes, 14)
        atr_ratio = self._atr_ratio(atr, 50)

        # Crisis detection: extreme ATR expansion + price crash
        returns = self._calc_returns(closes, 1)
        recent_return = returns[-1] if returns else 0.0

        if atr_ratio > 2.0 and recent_return < -0.03:
            return "CRISIS"

        if adx_val >= self.ADX_STRONG:
            return "TRENDING_UP" if ema_slope > 0 else "TRENDING_DOWN"

        if adx_val >= self.ADX_TREND_MIN:
            if atr_ratio > self.ATR_EXPAND_RATIO:
                return "HIGH_VOLATILITY"
            return "TRENDING_UP" if ema_slope > 0 else "TRENDING_DOWN"

        if adx_val <= self.ADX_RANGE_MAX:
            if atr_ratio < self.ATR_CONTRACT_RATIO:
                return "LOW_VOLATILITY"
            return "RANGING"

        # Ambiguous zone
        if atr_ratio > self.ATR_EXPAND_RATIO:
            return "HIGH_VOLATILITY"
        return "RANGING"

    # ------------------------------------------------------------------
    # Crypto detection (volatility clustering)
    # ------------------------------------------------------------------

    def _detect_crypto(self, data: Dict[str, Any]) -> str:
        """Detect crypto regime using volatility clustering and returns."""
        closes = self._extract_series(data, "closes", "close")
        volumes = self._extract_series(data, "volumes", "volume")

        if len(closes) < 30:
            return "ACCUMULATION"

        returns = self._calc_returns(closes, 1)
        vol_series = self._rolling_volatility(returns, 20)

        if not vol_series:
            return "ACCUMULATION"

        current_vol = vol_series[-1]
        vol_percentiles = self._percentiles(vol_series, [10, 90])

        # Regime logic
        ema50 = self._calc_ema(closes, 50)
        ema_slope = self._calc_slope(ema50, 5)
        recent_return_20 = self._calc_returns(closes, 20)
        trend_20 = recent_return_20[-1] if recent_return_20 else 0.0

        if current_vol >= vol_percentiles.get(90, 0.0):
            return "EXTREME_VOLATILITY"

        if trend_20 > 0.10 and ema_slope > 0:
            return "BULL"
        if trend_20 < -0.10 and ema_slope < 0:
            return "BEAR"

        # Accumulation/distribution: check volume trend
        if volumes and len(volumes) >= 20:
            vol_sma = sum(volumes[-20:]) / 20
            current_volume = volumes[-1]
            if current_volume < vol_sma * 0.7:
                return "ACCUMULATION"
            if current_volume > vol_sma * 1.5 and trend_20 < -0.05:
                return "DISTRIBUTION"

        return "ACCUMULATION"

    # ------------------------------------------------------------------
    # Forex detection (ADX-based)
    # ------------------------------------------------------------------

    def _detect_forex(self, data: Dict[str, Any]) -> str:
        """Detect forex regime using ADX and spread data."""
        closes = self._extract_series(data, "closes", "close")
        highs = self._extract_series(data, "highs", "high")
        lows = self._extract_series(data, "lows", "low")
        spreads = data.get("spreads") or data.get("spread")

        if len(closes) < 30:
            return "RANGING"

        adx = self._calc_adx(highs, lows, closes, 14)
        adx_val = adx[-1] if adx else 0.0

        atr = self._calc_atr(highs, lows, closes, 14)
        atr_ratio = self._atr_ratio(atr, 30)

        # Spread spike detection
        if spreads and isinstance(spreads, list) and len(spreads) >= 20:
            avg_spread = sum(spreads) / len(spreads)
            if avg_spread > 0 and spreads[-1] > avg_spread * 2.5:
                return "NEWS_DRIVEN"

        # Low liquidity: volume collapse or very low ATR
        volumes = self._extract_series(data, "volumes", "volume")
        if volumes and len(volumes) >= 20:
            vol_sma = sum(volumes[-20:]) / 20
            if vol_sma > 0 and volumes[-1] < vol_sma * 0.3:
                return "LOW_LIQUIDITY"

        if adx_val >= self.ADX_TREND_MIN:
            return "TRENDING"

        return "RANGING"

    # ------------------------------------------------------------------
    # Indices detection (VIX proxy)
    # ------------------------------------------------------------------

    def _detect_indices(self, data: Dict[str, Any]) -> str:
        """Detect indices regime using VIX proxy and volatility."""
        closes = self._extract_series(data, "closes", "close")
        vix = data.get("vix_proxy") or data.get("vix")

        if len(closes) < 20:
            return "LOW_VOL"

        returns = self._calc_returns(closes, 1)
        recent_return = returns[-1] if returns else 0.0

        atr = None
        highs = self._extract_series(data, "highs", "high")
        lows = self._extract_series(data, "lows", "low")
        if highs and lows and len(highs) >= 14:
            atr = self._calc_atr(highs, lows, closes, 14)
        atr_ratio = self._atr_ratio(atr, 20) if atr else 1.0

        # Crash detection
        if recent_return < -0.04 or atr_ratio > 2.5:
            return "CRASH"

        # VIX proxy
        if vix and isinstance(vix, list) and len(vix) >= 5:
            vix_current = vix[-1]
            if vix_current > 30:
                return "RISK_OFF"
            if vix_current < 15:
                return "LOW_VOL"

        # Earnings proxy: high intraday volatility with moderate close
        if highs and lows and len(highs) >= 2:
            intraday_range = (highs[-1] - lows[-1]) / closes[-1] if closes[-1] else 0
            if intraday_range > 0.02 and abs(recent_return) < 0.01:
                return "EARNINGS"

        # Trend-based
        ema20 = self._calc_ema(closes, 20)
        if ema20:
            slope = self._calc_slope(ema20, 3)
            if slope > 0.005:
                return "RISK_ON"
            if slope < -0.005:
                return "RISK_OFF"

        return "LOW_VOL"

    # ------------------------------------------------------------------
    # Technical indicator helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_series(
        data: Dict[str, Any], *keys: str
    ) -> List[float]:
        """Extract a numeric series from data dict, trying multiple key names."""
        for key in keys:
            val = data.get(key)
            if val and isinstance(val, list) and len(val) > 0:
                return [float(v) for v in val]
        return []

    @staticmethod
    def _calc_adx(
        highs: List[float], lows: List[float], closes: List[float], period: int
    ) -> List[float]:
        """Wilder's ADX."""
        if len(closes) < period + 1:
            return []
        tr: List[float] = []
        up_moves: List[float] = []
        down_moves: List[float] = []
        for i in range(1, len(closes)):
            hl = highs[i] - lows[i]
            hc = abs(highs[i] - closes[i - 1])
            lc = abs(lows[i] - closes[i - 1])
            tr.append(max(hl, hc, lc))
            um = highs[i] - highs[i - 1]
            dm = lows[i - 1] - lows[i]
            up_moves.append(um if um > dm and um > 0 else 0.0)
            down_moves.append(dm if dm > um and dm > 0 else 0.0)

        def _wilder_smooth(vals: List[float], p: int) -> List[float]:
            if not vals or p <= 1:
                return []
            result = [sum(vals[:p]) / p]
            for v in vals[p:]:
                result.append((result[-1] * (p - 1) + v) / p)
            return result

        atr_s = _wilder_smooth(tr, period)
        up_s = _wilder_smooth(up_moves, period)
        dn_s = _wilder_smooth(down_moves, period)
        n = min(len(atr_s), len(up_s), len(dn_s))
        dx: List[float] = []
        for i in range(n):
            if atr_s[i] > 0:
                pdi = 100 * up_s[i] / atr_s[i]
                ndi = 100 * dn_s[i] / atr_s[i]
                s = pdi + ndi
                dx.append(100 * abs(pdi - ndi) / s if s > 0 else 0.0)
            else:
                dx.append(0.0)
        return _wilder_smooth(dx, period)

    @staticmethod
    def _calc_ema(values: List[float], period: int) -> List[float]:
        """Exponential Moving Average."""
        if len(values) < period:
            return []
        mult = 2.0 / (period + 1)
        ema = [sum(values[:period]) / period]
        for v in values[period:]:
            ema.append((v - ema[-1]) * mult + ema[-1])
        return ema

    @staticmethod
    def _calc_slope(values: List[float], lookback: int) -> float:
        """Normalized slope over lookback bars."""
        if len(values) < lookback + 1:
            return 0.0
        recent = values[-(lookback + 1):]
        return (recent[-1] - recent[0]) / recent[0] if recent[0] != 0 else 0.0

    @staticmethod
    def _calc_atr(
        highs: List[float], lows: List[float], closes: List[float], period: int
    ) -> List[float]:
        """Average True Range (Wilder smoothing)."""
        if len(closes) < period + 1:
            return []
        tr: List[float] = []
        for i in range(1, len(closes)):
            hl = highs[i] - lows[i]
            hc = abs(highs[i] - closes[i - 1])
            lc = abs(lows[i] - closes[i - 1])
            tr.append(max(hl, hc, lc))

        def _wilder_smooth(vals: List[float], p: int) -> List[float]:
            if not vals or p <= 1:
                return []
            result = [sum(vals[:p]) / p]
            for v in vals[p:]:
                result.append((result[-1] * (p - 1) + v) / p)
            return result

        return _wilder_smooth(tr, period)

    @staticmethod
    def _calc_returns(prices: List[float], period: int) -> List[float]:
        """Calculate percentage returns over period bars."""
        if len(prices) <= period:
            return []
        return [
            (prices[i] - prices[i - period]) / prices[i - period]
            if prices[i - period] != 0
            else 0.0
            for i in range(period, len(prices))
        ]

    @staticmethod
    def _rolling_volatility(returns: List[float], window: int) -> List[float]:
        """Rolling standard deviation of returns."""
        if len(returns) < window:
            return []
        result: List[float] = []
        for i in range(window, len(returns) + 1):
            chunk = returns[i - window:i]
            mean = sum(chunk) / len(chunk)
            var = sum((x - mean) ** 2 for x in chunk) / len(chunk)
            result.append(var ** 0.5)
        return result

    @staticmethod
    def _percentiles(values: List[float], pcts: List[float]) -> Dict[float, float]:
        """Calculate percentiles from a list of values."""
        if not values:
            return {p: 0.0 for p in pcts}
        sorted_vals = sorted(values)
        result: Dict[float, float] = {}
        for pct in pcts:
            idx = int(len(sorted_vals) * pct / 100)
            idx = min(idx, len(sorted_vals) - 1)
            result[pct] = sorted_vals[idx]
        return result

    def _atr_ratio(self, atr: List[float], window: int) -> float:
        """Current ATR / SMA(ATR, window)."""
        if not atr:
            return 1.0
        current = atr[-1]
        if len(atr) < window:
            sma = sum(atr) / len(atr)
        else:
            sma = sum(atr[-window:]) / window
        return current / sma if sma > 0 else 1.0

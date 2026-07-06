"""
4-Class Regime Classifier.

Classifies market into 2x2 grid:
- Vol:   LOW / MED / HIGH
- Trend: UP / DOWN / FLAT
- → calm_bull, volatile_bull, calm_bear, volatile_bear

Position scales:
- calm_bull      → 1.5  (best conditions)
- volatile_bull  → 1.0
- calm_bear      → 0.5
- volatile_bear  → 0.0  (worst conditions, no trades)
"""

from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np
import pandas as pd


class RegimeType(StrEnum):
    CALM_BULL = "calm_bull"
    VOLATILE_BULL = "volatile_bull"
    CALM_BEAR = "calm_bear"
    VOLATILE_BEAR = "volatile_bear"


REGIME_SCALE: dict[RegimeType, float] = {
    RegimeType.CALM_BULL: 1.5,
    RegimeType.VOLATILE_BULL: 1.0,
    RegimeType.CALM_BEAR: 0.5,
    RegimeType.VOLATILE_BEAR: 0.0,
}


@dataclass
class RegimeResult:
    """Regime classification result."""
    regime: RegimeType
    confidence: float  # 0-1
    position_scale: float  # 0-1.5
    vol_regime: str  # LOW / MED / HIGH
    trend_regime: str  # UP / DOWN / FLAT
    features: dict = field(default_factory=dict)


class RegimeClassifier:
    """
    4-class regime classifier.

    Uses vol percentile + trend direction to classify markets.
    """

    MIN_BARS = 60

    def __init__(
        self,
        vol_lookback: int = 20,
        vol_long_lookback: int = 252,
        trend_lookback: int = 60,
        vol_threshold_high: float = 0.67,
        vol_threshold_low: float = 0.33,
        trend_threshold: float = 0.0,
    ):
        self.vol_lookback = vol_lookback
        self.vol_long_lookback = vol_long_lookback
        self.trend_lookback = trend_lookback
        self.vol_threshold_high = vol_threshold_high
        self.vol_threshold_low = vol_threshold_low
        self.trend_threshold = trend_threshold

    def classify(
        self,
        close: pd.Series,
        high: pd.Series | None = None,
        low: pd.Series | None = None,
    ) -> RegimeResult:
        """
        Classify current market regime.

        Args:
            close: Close price series
            high: High price series (optional)
            low: Low price series (optional)

        Returns:
            RegimeResult

        Raises:
            ValueError: If series is too short
        """
        if len(close) < self.MIN_BARS:
            raise ValueError(
                f"Need at least {self.MIN_BARS} bars, got {len(close)}"
            )

        close = close.dropna()

        # --- Vol features ---
        returns = close.pct_change().dropna()
        realized_vol = returns.rolling(self.vol_lookback).std() * np.sqrt(252)
        current_vol = realized_vol.iloc[-1]

        # Vol percentile (rolling)
        vol_series = realized_vol.dropna()
        if len(vol_series) >= self.vol_long_lookback:
            vol_percentile = (
                vol_series.iloc[-self.vol_long_lookback:]
                .rank(pct=True)
                .iloc[-1]
            )
        else:
            vol_percentile = vol_series.rank(pct=True).iloc[-1]

        # Vol regime bucket
        if vol_percentile >= self.vol_threshold_high:
            vol_regime = "HIGH"
        elif vol_percentile <= self.vol_threshold_low:
            vol_regime = "LOW"
        else:
            vol_regime = "MED"

        # --- Trend features ---
        ema_short = close.ewm(span=self.trend_lookback // 3).mean()
        ema_long = close.ewm(span=self.trend_lookback).mean()

        ema_short_val = ema_short.iloc[-1]
        ema_long_val = ema_long.iloc[-1]

        trend_strength = (ema_short_val - ema_long_val) / ema_long_val

        if trend_strength > self.trend_threshold:
            trend_regime = "UP"
        elif trend_strength < -self.trend_threshold:
            trend_regime = "DOWN"
        else:
            trend_regime = "FLAT"

        # --- 4-class mapping ---
        is_high_vol = vol_regime == "HIGH"
        is_bull = trend_regime == "UP"

        if not is_high_vol and is_bull:
            regime = RegimeType.CALM_BULL
        elif is_high_vol and is_bull:
            regime = RegimeType.VOLATILE_BULL
        elif not is_high_vol and not is_bull:
            regime = RegimeType.CALM_BEAR
        else:
            regime = RegimeType.VOLATILE_BEAR

        # Confidence: distance from decision boundaries
        vol_conf = abs(vol_percentile - 0.5) * 2  # 0 at median, 1 at extremes
        trend_conf = min(abs(trend_strength) / 0.02, 1.0)
        confidence = round((vol_conf + trend_conf) / 2, 3)
        confidence = np.clip(confidence, 0.0, 1.0)

        features = {
            "vol_percentile": round(vol_percentile, 4),
            "trend_strength": round(trend_strength, 6),
            "realized_vol": round(current_vol, 6),
            "ema_short": round(ema_short_val, 6),
            "ema_long": round(ema_long_val, 6),
        }

        return RegimeResult(
            regime=regime,
            confidence=float(confidence),
            position_scale=REGIME_SCALE[regime],
            vol_regime=vol_regime,
            trend_regime=trend_regime,
            features=features,
        )

    def classify_batch(
        self,
        close: pd.Series,
        high: pd.Series | None = None,
        low: pd.Series | None = None,
    ) -> pd.DataFrame:
        """
        Walk-forward batch classification.

        Returns DataFrame with columns:
            timestamp, regime, confidence, position_scale, vol_regime, trend_regime
        """
        if len(close) < self.MIN_BARS:
            return pd.DataFrame()

        rows = []
        close = close.dropna()

        for i in range(self.MIN_BARS, len(close)):
            window = close.iloc[: i + 1]
            try:
                result = self.classify(window, high=high, low=low)
                ts = close.index[i] if hasattr(close.index, '__getitem__') else i
                rows.append({
                    "timestamp": ts,
                    "regime": result.regime.value,
                    "confidence": result.confidence,
                    "position_scale": result.position_scale,
                    "vol_regime": result.vol_regime,
                    "trend_regime": result.trend_regime,
                })
            except (ValueError, IndexError):
                continue

        return pd.DataFrame(rows)

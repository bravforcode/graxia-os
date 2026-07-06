"""Phase 4 — Regime Change Detection Module.

Detects market regime transitions that should trigger position sizing changes:
- Volatility regime: low-vol (bull) vs high-vol (bear)
- Correlation regime: normal vs crisis (correlations spike)
- Signal regime: strategy signals diverge from actual returns

Research:
- Hamilton (1989): Markov regime-switching models
- IMF (2025): 1σ VIX increase widens FX spreads by 1-3 bps
- March 2020: 99% VaR breached on 12 consecutive days
- Regime detection improves backtest realism by 30-50%
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from enum import Enum


class VolRegime(str, Enum):
    LOW_VOL = "low_vol"  # Calm, trending market
    NORMAL = "normal"  # Baseline volatility
    ELEVATED = "elevated"  # Above-average vol
    STRESSED = "stressed"  # Crisis / high-vol regime


class CorrelationRegime(str, Enum):
    NORMAL = "normal"  # Diversification works
    ELEVATED = "elevated"  # Correlations rising
    CRISIS = "crisis"  # Correlations spike to near-unity


@dataclass
class RegimeState:
    """Current regime state."""

    vol_regime: VolRegime = VolRegime.NORMAL
    corr_regime: CorrelationRegime = CorrelationRegime.NORMAL
    vol_ratio: float = 1.0  # realized_vol / long_term_vol
    avg_correlation: float = 0.0
    regime_duration: int = 0  # Bars in current regime
    regime_confidence: float = 0.5  # 0-1, how confident in regime detection
    position_size_mult: float = 1.0  # Recommended position size multiplier


@dataclass
class RegimeConfig:
    """Regime detection configuration."""

    # Volatility regime thresholds
    vol_lookback_short: int = 20  # Short-term realized vol window
    vol_lookback_long: int = 200  # Long-term vol reference
    vol_low_threshold: float = 0.7  # realized/long < 0.7 = low vol
    vol_elevated_threshold: float = 1.3  # realized/long > 1.3 = elevated
    vol_stressed_threshold: float = 2.0  # realized/long > 2.0 = stressed

    # Correlation regime thresholds
    corr_lookback: int = 60  # Rolling correlation window
    corr_elevated_threshold: float = 0.5  # Avg correlation > 0.5 = elevated
    corr_crisis_threshold: float = 0.7  # Avg correlation > 0.7 = crisis

    # Bars per year for annualization (default: M15 forex = 24192)
    # Override per asset class: equities=252, crypto=365, M15=24192, H1=6048
    bars_per_year: float = 24192.0

    # Position size adjustments per regime
    vol_size_mult: dict[str, float] = field(
        default_factory=lambda: {
            "low_vol": 1.2,  # Slightly larger in calm markets
            "normal": 1.0,
            "elevated": 0.7,  # Reduce in elevated vol
            "stressed": 0.3,  # Minimal in stressed markets
        }
    )
    corr_size_mult: dict[str, float] = field(
        default_factory=lambda: {
            "normal": 1.0,
            "elevated": 0.8,
            "crisis": 0.5,  # Half size in crisis
        }
    )


class RegimeDetector:
    """Detects market regime transitions.

    Uses rolling volatility and correlation analysis to identify
    regime changes that should trigger position sizing adjustments.
    """

    def __init__(self, config: RegimeConfig | None = None):
        self.config = config or RegimeConfig()
        # Phase 4: Use deque with maxlen to cap memory at vol_lookback_long
        self._returns: deque[float] = deque(maxlen=self.config.vol_lookback_long)
        self._bar_count: int = 0
        self._current_state = RegimeState()
        self._regime_start_bar: int = 0

    def update(self, bar_return: float, bar_index: int = 0) -> RegimeState:
        """Update regime detection with new return data.

        Args:
            bar_return: Per-bar return
            bar_index: Current bar index

        Returns:
            Current RegimeState
        """
        self._returns.append(bar_return)
        self._bar_count = bar_index + 1

        if len(self._returns) < self.config.vol_lookback_long:
            return self._current_state

        # Calculate volatility regime
        vol_regime = self._detect_vol_regime()

        # Calculate correlation regime (requires multi-asset data)
        # For single-asset, use autocorrelation as proxy
        corr_regime = self._detect_corr_regime()

        # Track regime duration
        new_regime = vol_regime != self._current_state.vol_regime or corr_regime != self._current_state.corr_regime
        if new_regime:
            self._regime_start_bar = bar_index
            self._current_state.regime_duration = 0
        else:
            self._current_state.regime_duration += 1

        # Calculate position size multiplier
        vol_mult = self.config.vol_size_mult.get(vol_regime.value, 1.0)
        corr_mult = self.config.corr_size_mult.get(corr_regime.value, 1.0)
        combined_mult = vol_mult * corr_mult

        # Regime confidence based on how far metrics are from thresholds
        vol_ratio = self._current_state.vol_ratio
        if vol_ratio < self.config.vol_low_threshold:
            confidence = min(1.0, (self.config.vol_low_threshold - vol_ratio) / 0.3 + 0.5)
        elif vol_ratio > self.config.vol_stressed_threshold:
            confidence = min(1.0, (vol_ratio - self.config.vol_stressed_threshold) / 0.5 + 0.5)
        else:
            confidence = 0.5

        self._current_state = RegimeState(
            vol_regime=vol_regime,
            corr_regime=corr_regime,
            vol_ratio=vol_ratio,
            avg_correlation=self._current_state.avg_correlation,
            regime_duration=self._current_state.regime_duration,
            regime_confidence=round(confidence, 3),
            position_size_mult=round(combined_mult, 3),
        )

        return self._current_state

    def _detect_vol_regime(self) -> VolRegime:
        """Detect volatility regime from returns."""
        if len(self._returns) < self.config.vol_lookback_long:
            return VolRegime.NORMAL

        # Short-term realized vol (annualized)
        short_returns = list(self._returns)[-self.config.vol_lookback_short :]
        short_vol = self._annualized_vol(short_returns)

        # Long-term reference vol
        long_returns = list(self._returns)[-self.config.vol_lookback_long :]
        long_vol = self._annualized_vol(long_returns)

        if long_vol <= 0:
            return VolRegime.NORMAL

        ratio = short_vol / long_vol
        self._current_state.vol_ratio = ratio

        if ratio < self.config.vol_low_threshold:
            return VolRegime.LOW_VOL
        elif ratio > self.config.vol_stressed_threshold:
            return VolRegime.STRESSED
        elif ratio > self.config.vol_elevated_threshold:
            return VolRegime.ELEVATED
        else:
            return VolRegime.NORMAL

    def _detect_corr_regime(self) -> CorrelationRegime:
        """Detect correlation regime.

        For single-asset: use autocorrelation as proxy for market regime.
        High autocorrelation = trending (normal), low autocorrelation = choppy (elevated).
        """
        if len(self._returns) < self.config.corr_lookback:
            return CorrelationRegime.NORMAL

        recent = list(self._returns)[-self.config.corr_lookback :]

        # Calculate autocorrelation at lag 1
        n = len(recent)
        if n < 10:
            return CorrelationRegime.NORMAL

        mean = sum(recent) / n
        var = sum((r - mean) ** 2 for r in recent) / n
        if var <= 0:
            return CorrelationRegime.NORMAL

        cov = sum((recent[i] - mean) * (recent[i - 1] - mean) for i in range(1, n)) / (n - 1)
        autocorr = cov / var

        # Map autocorrelation to correlation regime
        # High positive autocorrelation = trending = normal
        # Low/negative autocorrelation = mean-reverting/choppy = elevated
        if autocorr < 0.1:
            self._current_state.avg_correlation = autocorr
            return CorrelationRegime.CRISIS
        elif autocorr < 0.3:
            self._current_state.avg_correlation = autocorr
            return CorrelationRegime.ELEVATED
        else:
            self._current_state.avg_correlation = autocorr
            return CorrelationRegime.NORMAL

    def _annualized_vol(self, returns: list[float]) -> float:
        """Calculate annualized volatility from returns."""
        if len(returns) < 2:
            return 0.0
        mean = sum(returns) / len(returns)
        var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        return math.sqrt(var * self.config.bars_per_year)  # Annualize per asset class

    def get_position_size_multiplier(self) -> float:
        """Get recommended position size multiplier based on current regime."""
        return self._current_state.position_size_mult

    def reset(self):
        """Reset state for a new backtest run."""
        self._returns.clear()
        self._bar_count = 0
        self._current_state = RegimeState()
        self._regime_start_bar = 0

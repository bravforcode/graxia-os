"""Phase 4 — Time-Varying Correlation (EWMA).

Replaces static correlation matrices with exponentially weighted
moving average (EWMA) correlations that adapt to market conditions.

Research:
- RiskMetrics (1996): λ=0.94 for daily data
- DCC-GARCH: more complex but captures asymmetric effects
- Static correlations underestimate portfolio drawdown by 30-50%
- March 2020: correlations spiked to near-unity
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class EWMAConfig:
    """EWMA correlation configuration."""

    lambda_decay: float = 0.94  # RiskMetrics standard for daily
    min_observations: int = 30  # Minimum data points before correlation is valid
    max_assets: int = 50  # Maximum assets for correlation matrix
    shrinkage_intensity: float = 0.1  # Ledoit-Wolf shrinkage toward identity


class EWMACorrelation:
    """Exponentially weighted moving average correlation tracker.

    Maintains a dynamic correlation matrix that adapts to changing
    market conditions, replacing static correlations.
    """

    def __init__(self, config: EWMAConfig | None = None):
        self.config = config or EWMAConfig()
        # Phase 4: Use counter instead of storing all returns (saves memory)
        self._return_counts: dict[str, int] = {}
        self._ewma_mean: dict[str, float] = {}
        self._ewma_var: dict[str, float] = {}
        self._ewma_covar: dict[tuple[str, str], float] = {}
        self._count: int = 0

    def update(self, returns: dict[str, float]):
        """Update with new return data.

        Args:
            returns: Dict mapping asset symbol → return for this bar
        """
        self._count += 1

        for sym, ret in returns.items():
            # Phase 4: Count returns instead of storing them (saves memory)
            self._return_counts[sym] = self._return_counts.get(sym, 0) + 1

            # Update EWMA mean
            old_mean = self._ewma_mean.get(sym, ret)
            new_mean = self.config.lambda_decay * old_mean + (1 - self.config.lambda_decay) * ret
            self._ewma_mean[sym] = new_mean

            # Update EWMA variance
            old_var = self._ewma_var.get(sym, 0.0)
            new_var = self.config.lambda_decay * old_var + (1 - self.config.lambda_decay) * (ret - new_mean) ** 2
            self._ewma_var[sym] = new_var

        # Update pairwise EWMA covariances
        symbols = list(returns.keys())
        for i, s1 in enumerate(symbols):
            for s2 in symbols[i + 1:]:
                r1 = returns[s1]
                r2 = returns[s2]
                m1 = self._ewma_mean.get(s1, r1)
                m2 = self._ewma_mean.get(s2, r2)

                key = (s1, s2) if s1 < s2 else (s2, s1)
                old_cov = self._ewma_covar.get(key, 0.0)
                new_cov = self.config.lambda_decay * old_cov + (1 - self.config.lambda_decay) * (r1 - m1) * (r2 - m2)
                self._ewma_covar[key] = new_cov

    def get_correlation(self, sym1: str, sym2: str) -> float:
        """Get current EWMA correlation between two assets.

        Args:
            sym1: First asset symbol
            sym2: Second asset symbol

        Returns:
            Correlation coefficient (-1 to 1)
        """
        if sym1 == sym2:
            return 1.0

        key = (sym1, sym2) if sym1 < sym2 else (sym2, sym1)
        cov = self._ewma_covar.get(key, 0.0)
        var1 = self._ewma_var.get(sym1, 0.0)
        var2 = self._ewma_var.get(sym2, 0.0)

        if var1 <= 0 or var2 <= 0:
            return 0.0

        corr = cov / math.sqrt(var1 * var2)
        return max(-1.0, min(1.0, corr))

    def get_correlation_matrix(self) -> dict[tuple[str, str], float]:
        """Get current EWMA correlation matrix.

        Returns:
            Dict mapping (sym1, sym2) → correlation
        """
        symbols = list(self._return_counts.keys())
        matrix = {}

        for i, s1 in enumerate(symbols):
            for s2 in symbols[i:]:
                corr = self.get_correlation(s1, s2)
                matrix[(s1, s2)] = corr
                if s1 != s2:
                    matrix[(s2, s1)] = corr

        return matrix

    def get_average_correlation(self) -> float:
        """Get average pairwise correlation across all assets.

        Useful for regime detection (high avg correlation = crisis).
        """
        symbols = list(self._return_counts.keys())
        if len(symbols) < 2:
            return 0.0

        total_corr = 0.0
        count = 0
        for i, s1 in enumerate(symbols):
            for s2 in symbols[i + 1:]:
                total_corr += self.get_correlation(s1, s2)
                count += 1

        return total_corr / count if count > 0 else 0.0

    def shrink_toward_identity(self, correlation: float) -> float:
        """Apply Ledoit-Wolf shrinkage toward identity.

        Stabilizes correlation estimates with limited data.
        """
        return (1 - self.config.shrinkage_intensity) * correlation + self.config.shrinkage_intensity * (1.0 if correlation == 1.0 else 0.0)

    def reset(self):
        """Reset state."""
        self._return_counts.clear()
        self._ewma_mean.clear()
        self._ewma_var.clear()
        self._ewma_covar.clear()
        self._count = 0

"""
Rolling Re-Validation Auto-Pause Gate (G10)

Monitors live/paper trading Sharpe ratio against a reference baseline.
Automatically pauses order submission when performance degrades below threshold.

Hard gate — not a recommendation. If trailing Sharpe drops below floor
or degrades >50% vs. reference, trading is paused until human review.

Usage:
    gate = RollingRevalidationGate(
        reference_sharpe=1.2,       # From Phase 2 paper trading
        sharpe_floor=0.3,           # Minimum acceptable live Sharpe
        degradation_threshold=0.50, # Max allowed degradation (50%)
        trailing_window_days=63,    # ~3 months of daily data
    )
    result = gate.check(daily_returns)
    if result.should_pause:
        # AUTO-PAUSE: stop order submission
        ...
"""

from __future__ import annotations

import numpy as np


class RevalidationResult:
    """Result of a rolling re-validation check."""

    def __init__(
        self,
        trailing_sharpe: float,
        reference_sharpe: float,
        sharpe_floor: float,
        degradation_pct: float,
        should_pause: bool,
        pause_reason: str,
        trailing_window_days: int,
        n_observations: int,
    ):
        self.trailing_sharpe = trailing_sharpe
        self.reference_sharpe = reference_sharpe
        self.sharpe_floor = sharpe_floor
        self.degradation_pct = degradation_pct
        self.should_pause = should_pause
        self.pause_reason = pause_reason
        self.trailing_window_days = trailing_window_days
        self.n_observations = n_observations

    def to_dict(self) -> dict:
        return {
            "trailing_sharpe": round(self.trailing_sharpe, 4),
            "reference_sharpe": round(self.reference_sharpe, 4),
            "sharpe_floor": self.sharpe_floor,
            "degradation_pct": round(self.degradation_pct * 100, 2),
            "should_pause": self.should_pause,
            "pause_reason": self.pause_reason,
            "trailing_window_days": self.trailing_window_days,
            "n_observations": self.n_observations,
        }


class RollingRevalidationGate:
    """Auto-pause gate based on trailing Sharpe ratio.

    Pauses trading when:
    1. Trailing Sharpe < sharpe_floor (absolute floor), OR
    2. Trailing Sharpe degraded > degradation_threshold vs. reference (relative)
    """

    def __init__(
        self,
        reference_sharpe: float,
        sharpe_floor: float = 0.3,
        degradation_threshold: float = 0.50,
        trailing_window_days: int = 63,
        min_observations: int = 20,
    ):
        """
        Args:
            reference_sharpe: Sharpe ratio from Phase 2 paper trading baseline.
            sharpe_floor: Minimum acceptable trailing Sharpe (absolute).
            degradation_threshold: Max allowed degradation as fraction (0.50 = 50%).
            trailing_window_days: Rolling window for Sharpe computation (~3 months).
            min_observations: Minimum data points required before gating.
        """
        self.reference_sharpe = reference_sharpe
        self.sharpe_floor = sharpe_floor
        self.degradation_threshold = degradation_threshold
        self.trailing_window_days = trailing_window_days
        self.min_observations = min_observations

    def check(self, daily_returns: np.ndarray | list[float]) -> RevalidationResult:
        """Check if trading should be paused based on trailing performance.

        Args:
            daily_returns: Array of daily percentage returns (e.g., [0.001, -0.002, ...]).

        Returns:
            RevalidationResult with should_pause flag and reason.
        """
        returns = np.asarray(daily_returns, dtype=float)
        returns = returns[~np.isnan(returns)]

        if len(returns) < self.min_observations:
            return RevalidationResult(
                trailing_sharpe=0.0,
                reference_sharpe=self.reference_sharpe,
                sharpe_floor=self.sharpe_floor,
                degradation_pct=0.0,
                should_pause=False,
                pause_reason="insufficient_data",
                trailing_window_days=self.trailing_window_days,
                n_observations=len(returns),
            )

        # Use trailing window
        window = returns[-self.trailing_window_days:] if len(returns) > self.trailing_window_days else returns
        mu = float(np.mean(window))
        std = float(np.std(window, ddof=1))
        trailing_sharpe = mu / (std + 1e-10) * np.sqrt(252)

        # Check absolute floor
        if trailing_sharpe < self.sharpe_floor:
            return RevalidationResult(
                trailing_sharpe=trailing_sharpe,
                reference_sharpe=self.reference_sharpe,
                sharpe_floor=self.sharpe_floor,
                degradation_pct=1.0 - (trailing_sharpe / (self.reference_sharpe + 1e-10)),
                should_pause=True,
                pause_reason=f"trailing_sharpe={trailing_sharpe:.4f} < floor={self.sharpe_floor}",
                trailing_window_days=self.trailing_window_days,
                n_observations=len(window),
            )

        # Check relative degradation
        if self.reference_sharpe > 0:
            degradation = 1.0 - (trailing_sharpe / self.reference_sharpe)
            if degradation > self.degradation_threshold:
                return RevalidationResult(
                    trailing_sharpe=trailing_sharpe,
                    reference_sharpe=self.reference_sharpe,
                    sharpe_floor=self.sharpe_floor,
                    degradation_pct=degradation,
                    should_pause=True,
                    pause_reason=f"degradation={degradation*100:.1f}% > threshold={self.degradation_threshold*100:.0f}%",
                    trailing_window_days=self.trailing_window_days,
                    n_observations=len(window),
                )

        return RevalidationResult(
            trailing_sharpe=trailing_sharpe,
            reference_sharpe=self.reference_sharpe,
            sharpe_floor=self.sharpe_floor,
            degradation_pct=0.0,
            should_pause=False,
            pause_reason="ok",
            trailing_window_days=self.trailing_window_days,
            n_observations=len(window),
        )

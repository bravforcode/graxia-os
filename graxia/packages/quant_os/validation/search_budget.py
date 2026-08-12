"""Strategy search budget tracker — counts trials for correct DSR calculation.

The core insight from Bailey & Lopez de Prado (2014) is that the number of
configurations tried during research must be accounted for when evaluating
Sharpe ratios. This module tracks that count and integrates with DSR.

Usage:
    tracker = SearchBudgetTracker(max_trials=1000)
    tracker.record_trial("strategy_a", {"ema_fast": 10, "ema_slow": 50}, is_sharpe=1.5)
    tracker.record_trial("strategy_a", {"ema_fast": 15, "ema_slow": 50}, is_sharpe=1.8)
    # ... many trials later ...
    dsr = tracker.get_deflated_sharpe("strategy_a", observed_sharpe=1.8, n_observations=5000)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from .deflated_sharpe import DeflatedSharpeResult, deflated_sharpe_ratio


@dataclass
class TrialRecord:
    strategy_id: str
    params: dict[str, float]
    timestamp: str
    in_sample_sharpe: float
    out_of_sample_sharpe: float | None = None


@dataclass
class SearchBudgetSummary:
    strategy_id: str
    total_trials: int
    max_trials: int
    within_budget: bool
    unique_param_sets: int
    best_is_sharpe: float
    best_oos_sharpe: float | None


class SearchBudgetTracker:
    """Track strategy search trials and compute budget-aware DSR.

    Args:
        max_trials: Maximum allowed trials per strategy (default 1000)
    """

    def __init__(self, max_trials: int = 1000):
        self.max_trials = max_trials
        self._trials: dict[str, list[TrialRecord]] = {}  # strategy_id -> trials

    def record_trial(
        self,
        strategy_id: str,
        params: dict[str, float],
        is_sharpe: float,
        oos_sharpe: float | None = None,
    ) -> None:
        """Record a strategy trial."""
        record = TrialRecord(
            strategy_id=strategy_id,
            params=dict(params),
            timestamp=datetime.now(UTC).isoformat(),
            in_sample_sharpe=is_sharpe,
            out_of_sample_sharpe=oos_sharpe,
        )
        if strategy_id not in self._trials:
            self._trials[strategy_id] = []
        self._trials[strategy_id].append(record)

    def get_trial_count(self, strategy_id: str) -> int:
        """Get number of trials for a strategy."""
        return len(self._trials.get(strategy_id, []))

    def get_total_trials(self) -> int:
        """Get total trials across all strategies."""
        return sum(len(trials) for trials in self._trials.values())

    def is_within_budget(self, strategy_id: str) -> bool:
        """Check if strategy is within search budget."""
        return self.get_trial_count(strategy_id) <= self.max_trials

    def get_deflated_sharpe(
        self,
        strategy_id: str,
        observed_sharpe: float,
        n_observations: int,
        skewness: float = 0.0,
        kurtosis: float = 3.0,
        confidence_level: float = 0.95,
    ) -> DeflatedSharpeResult:
        """Compute DSR using the actual recorded trial count as n_trials.

        This is the key integration point — the user doesn't need to manually
        track how many configurations were tried.
        """
        # Get trial count for this strategy, fall back to 1 if no trials recorded
        n_trials = max(self.get_trial_count(strategy_id), 1)
        return deflated_sharpe_ratio(
            observed_sharpe=observed_sharpe,
            n_trials=n_trials,
            n_observations=n_observations,
            skewness=skewness,
            kurtosis=kurtosis,
            confidence_level=confidence_level,
        )

    def summary(self, strategy_id: str) -> SearchBudgetSummary:
        """Get summary for a strategy."""
        trials = self._trials.get(strategy_id, [])
        total = len(trials)
        unique = len({frozenset(t.params.items()) for t in trials})
        best_is = max((t.in_sample_sharpe for t in trials), default=0.0)
        oos_values = [t.out_of_sample_sharpe for t in trials if t.out_of_sample_sharpe is not None]
        best_oos = max(oos_values) if oos_values else None
        return SearchBudgetSummary(
            strategy_id=strategy_id,
            total_trials=total,
            max_trials=self.max_trials,
            within_budget=total <= self.max_trials,
            unique_param_sets=unique,
            best_is_sharpe=best_is,
            best_oos_sharpe=best_oos,
        )

    def reset(self, strategy_id: str | None = None) -> None:
        """Clear recorded trials."""
        if strategy_id is None:
            self._trials.clear()
        else:
            self._trials.pop(strategy_id, None)

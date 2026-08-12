"""Parameter sweep from vectorbt pattern — with automatic search-budget tracking."""

from collections.abc import Callable
from itertools import product

from ..validation.search_budget import SearchBudgetTracker


class ParamSweep:
    """
    Parameter sweep with broadcasting (vectorbt pattern).

    Automatically records every trial to SearchBudgetTracker when strategy_id
    is provided, enabling correct Deflated Sharpe Ratio calculation without
    manual record_trial() calls.

    Usage:
        sweep = ParamSweep(
            {"ema_fast": [5, 10, 15, 20], "ema_slow": [20, 30, 40, 50]},
            strategy_id="xau_v1",
            budget=1000,
        )

        def evaluate(params):
            strategy = create_strategy(**params)
            result = backtest(strategy)
            return result.sharpe_ratio

        results = sweep.run(evaluate)
        best = sweep.get_best(results)

        # Automatic — no manual record_trial() needed
        dsr = sweep.get_deflated_sharpe(observed_sharpe=best[1], n_observations=5000)
    """

    def __init__(
        self,
        param_grid: dict[str, list],
        *,
        strategy_id: str | None = None,
        budget: int = 1000,
    ):
        self.param_grid = param_grid
        self.param_names = list(param_grid.keys())
        self.param_values = list(param_grid.values())
        self.combinations = list(product(*self.param_values))
        self.strategy_id = strategy_id or "default"
        self._tracker = SearchBudgetTracker(max_trials=budget)

    @property
    def n_combinations(self) -> int:
        return len(self.combinations)

    @property
    def tracker(self) -> SearchBudgetTracker:
        """Access the underlying search-budget tracker."""
        return self._tracker

    def run(self, evaluate_fn: Callable[[dict], float], show_progress: bool = True) -> list[tuple[dict, float]]:
        """Run evaluation for all parameter combinations.

        Each trial is automatically recorded to the SearchBudgetTracker when a
        strategy_id was provided at construction time.
        """
        results = []
        total = self.n_combinations

        for i, combo in enumerate(self.combinations):
            params = dict(zip(self.param_names, combo, strict=False))

            if show_progress:
                print(f"\r  Sweep: {i+1}/{total} ({(i+1)/total*100:.1f}%)", end="", flush=True)

            try:
                score = evaluate_fn(params)
                results.append((params, score))
            except Exception:
                score = float("-inf")
                results.append((params, score))

            # Auto-record trial to budget tracker
            if self.strategy_id:
                self._tracker.record_trial(self.strategy_id, params, is_sharpe=score)

        if show_progress:
            print()

        # Sort by score (descending)
        results.sort(key=lambda x: x[1], reverse=True)

        return results

    def get_deflated_sharpe(
        self,
        observed_sharpe: float,
        n_observations: int,
        *,
        skewness: float = 0.0,
        kurtosis: float = 3.0,
        confidence_level: float = 0.95,
    ):
        """Compute Deflated Sharpe Ratio using the auto-recorded trial count."""
        return self._tracker.get_deflated_sharpe(
            strategy_id=self.strategy_id,
            observed_sharpe=observed_sharpe,
            n_observations=n_observations,
            skewness=skewness,
            kurtosis=kurtosis,
            confidence_level=confidence_level,
        )

    def budget_summary(self):
        """Return the SearchBudgetSummary for this sweep's strategy."""
        return self._tracker.summary(self.strategy_id)

    def get_best(self, results: list[tuple[dict, float]]) -> tuple[dict, float]:
        """Get best parameter combination"""
        if not results:
            return {}, float("-inf")
        return results[0]

    def get_top_n(self, results: list[tuple[dict, float]], n: int = 5) -> list[tuple[dict, float]]:
        """Get top N parameter combinations"""
        return results[:n]

    def summary(self, results: list[tuple[dict, float]]) -> str:
        """Generate summary text"""
        lines = [f"Parameter Sweep Results ({self.n_combinations} combinations)"]
        lines.append("=" * 50)

        for i, (params, score) in enumerate(results[:10]):
            param_str = ", ".join(f"{k}={v}" for k, v in params.items())
            lines.append(f"  #{i+1}: {score:.4f} | {param_str}")

        if len(results) > 10:
            lines.append(f"  ... and {len(results) - 10} more")

        return "\n".join(lines)

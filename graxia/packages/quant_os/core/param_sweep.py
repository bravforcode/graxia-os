"""Parameter sweep from vectorbt pattern"""

from collections.abc import Callable
from itertools import product


class ParamSweep:
    """
    Parameter sweep with broadcasting (vectorbt pattern).

    Usage:
        sweep = ParamSweep({
            "ema_fast": [5, 10, 15, 20],
            "ema_slow": [20, 30, 40, 50],
            "rsi_threshold": [60, 70, 80],
        })

        def evaluate(params):
            strategy = create_strategy(**params)
            result = backtest(strategy)
            return result.sharpe_ratio

        results = sweep.run(evaluate)
        best = sweep.get_best(results)
    """

    def __init__(self, param_grid: dict[str, list]):
        self.param_grid = param_grid
        self.param_names = list(param_grid.keys())
        self.param_values = list(param_grid.values())
        self.combinations = list(product(*self.param_values))

    @property
    def n_combinations(self) -> int:
        return len(self.combinations)

    def run(self, evaluate_fn: Callable[[dict], float], show_progress: bool = True) -> list[tuple[dict, float]]:
        """Run evaluation for all parameter combinations"""
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
                results.append((params, float("-inf")))

        if show_progress:
            print()

        # Sort by score (descending)
        results.sort(key=lambda x: x[1], reverse=True)

        return results

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

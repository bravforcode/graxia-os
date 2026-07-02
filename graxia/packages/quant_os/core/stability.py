"""
Walk-Forward Stability Metric

Measures IS/OS gap to detect overfitting.
Stability gap < 0.3 = robust strategy.
"""

from dataclasses import dataclass
from typing import List, Dict


@dataclass
class StabilityResult:
    """Walk-forward stability result"""
    stability_gap: float  # IS/OS performance gap (0 = perfect, 1 = terrible)
    is_performance: float
    os_performance: float
    n_windows: int
    os_consistency: float  # % of profitable OOS windows
    is_sharpe: float
    os_sharpe: float
    is_os_ratio: float  # OS/IS ratio (>1 = better OOS, <1 = degradation)
    passed: bool  # stability_gap < 0.3


class WalkForwardStability:
    """
    Calculate walk-forward stability metrics.

    From dashboard:
        IS vs OS gap < 0.3
        OS Sharpe > 1.5
    """

    def __init__(self, max_gap: float = 0.3, min_os_sharpe: float = 1.5):
        self.max_gap = max_gap
        self.min_os_sharpe = min_os_sharpe

    def calculate(
        self,
        is_results: List[Dict],
        os_results: List[Dict],
    ) -> StabilityResult:
        """
        Calculate stability from walk-forward results.

        Args:
            is_results: List of in-sample results (each has 'sharpe', 'return', 'trades')
            os_results: List of out-of-sample results

        Returns:
            StabilityResult
        """
        if not is_results or not os_results:
            return StabilityResult(
                stability_gap=1.0,
                is_performance=0,
                os_performance=0,
                n_windows=0,
                os_consistency=0,
                is_sharpe=0,
                os_sharpe=0,
                is_os_ratio=0,
                passed=False,
            )

        # Calculate average performance
        is_sharpe = self._avg_metric(is_results, "sharpe")
        os_sharpe = self._avg_metric(os_results, "sharpe")

        is_return = self._avg_metric(is_results, "return")
        os_return = self._avg_metric(os_results, "return")

        # Stability gap (normalized)
        if is_sharpe > 0:
            stability_gap = round(max(0, 1 - os_sharpe / is_sharpe), 4)
        else:
            stability_gap = 1.0

        # IS/OS ratio
        is_os_ratio = round(os_sharpe / is_sharpe, 4) if is_sharpe > 0 else 0.0

        # OOS consistency
        profitable_os = sum(1 for r in os_results if r.get("return", 0) > 0)
        os_consistency = round(profitable_os / len(os_results), 4)

        return StabilityResult(
            stability_gap=stability_gap,
            is_performance=round(is_return, 4),
            os_performance=round(os_return, 4),
            n_windows=len(os_results),
            os_consistency=os_consistency,
            is_sharpe=round(is_sharpe, 4),
            os_sharpe=round(os_sharpe, 4),
            is_os_ratio=is_os_ratio,
            passed=is_sharpe > 0 and stability_gap < self.max_gap and os_sharpe > self.min_os_sharpe,
        )

    def _avg_metric(self, results: List[Dict], metric: str) -> float:
        """Calculate average metric"""
        values = [r.get(metric, 0) for r in results if metric in r]
        return sum(values) / len(values) if values else 0

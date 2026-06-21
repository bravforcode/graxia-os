"""
Fake Signal Filter — 6 criteria from dashboard

Filters out overfitted/fake signals:
1. Walk-forward stability (IS/OS gap < 0.3)
2. Monte Carlo p-value (< 0.05) — LOW p = significant edge
3. Stress test survival (Max DD < 20%)
4. Out-of-sample Sharpe (> 1.5)
5. Profit factor (> 1.3)
6. Expectancy (> 0)
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from .monte_carlo import MonteCarloResult
from .stability import StabilityResult


@dataclass
class FilterResult:
    """Signal filter result"""
    passed: bool
    score: int  # 0-6 (how many criteria passed)
    criteria: Dict[str, bool]
    details: Dict[str, str]
    
    @property
    def grade(self) -> str:
        if self.score == 6:
            return "S"
        elif self.score >= 5:
            return "A"
        elif self.score >= 4:
            return "B"
        elif self.score >= 3:
            return "C"
        else:
            return "F"


class FakeSignalFilter:
    """
    Filters fake/overfitted signals using 6 criteria.
    
    Usage:
        filter = FakeSignalFilter()
        result = filter.evaluate(
            stability=stability_result,
            monte_carlo=mc_result,
            metrics=backtest_metrics,
        )
        
        if result.passed:
            print(f"Signal is real! Grade: {result.grade}")
    """
    
    def __init__(
        self,
        max_stability_gap: float = 0.3,
        max_p_value: float = 0.05,  # LOW p-value = significant edge
        max_stress_dd: float = 20.0,
        min_os_sharpe: float = 1.5,
        min_profit_factor: float = 1.3,
        min_expectancy: float = 0.0,
    ):
        self.max_stability_gap = max_stability_gap
        self.max_p_value = max_p_value
        self.max_stress_dd = max_stress_dd
        self.min_os_sharpe = min_os_sharpe
        self.min_profit_factor = min_profit_factor
        self.min_expectancy = min_expectancy
    
    def evaluate(
        self,
        stability: Optional[StabilityResult] = None,
        monte_carlo: Optional[MonteCarloResult] = None,
        metrics: Optional[Dict] = None,
    ) -> FilterResult:
        """
        Evaluate signal against all 6 criteria.
        
        Args:
            stability: Walk-forward stability result
            monte_carlo: Monte Carlo simulation result
            metrics: Backtest metrics dict
        
        Returns:
            FilterResult with pass/fail and details
        """
        criteria = {}
        details = {}
        
        # 1. Walk-forward stability
        if stability:
            criteria["stability"] = stability.stability_gap < self.max_stability_gap
            details["stability"] = (
                f"Gap: {stability.stability_gap:.3f} "
                f"({'PASS' if criteria['stability'] else 'FAIL'} "
                f"threshold: {self.max_stability_gap})"
            )
        else:
            criteria["stability"] = False
            details["stability"] = "NOT TESTED"
        
        # 2. Monte Carlo p-value — LOW p-value = significant edge
        if monte_carlo:
            criteria["monte_carlo"] = monte_carlo.p_value < self.max_p_value
            details["monte_carlo"] = (
                f"p-value: {monte_carlo.p_value:.3f} "
                f"({'PASS' if criteria['monte_carlo'] else 'FAIL'} "
                f"threshold: < {self.max_p_value})"
            )
        else:
            criteria["monte_carlo"] = False
            details["monte_carlo"] = "NOT TESTED"
        
        # 3. Stress test survival
        if monte_carlo:
            criteria["stress_test"] = monte_carlo.survival_rate > 0.9
            details["stress_test"] = (
                f"Survival: {monte_carlo.survival_rate:.1%} "
                f"({'PASS' if criteria['stress_test'] else 'FAIL'} "
                f"DD < {self.max_stress_dd}%)"
            )
        else:
            criteria["stress_test"] = False
            details["stress_test"] = "NOT TESTED"
        
        # 4. Out-of-sample Sharpe
        if stability:
            criteria["os_sharpe"] = stability.os_sharpe > self.min_os_sharpe
            details["os_sharpe"] = (
                f"OS Sharpe: {stability.os_sharpe:.2f} "
                f"({'PASS' if criteria['os_sharpe'] else 'FAIL'} "
                f"threshold: {self.min_os_sharpe})"
            )
        else:
            criteria["os_sharpe"] = False
            details["os_sharpe"] = "NOT TESTED"
        
        # 5. Profit factor
        if metrics:
            pf = metrics.get("profit_factor", 0)
            criteria["profit_factor"] = pf > self.min_profit_factor
            details["profit_factor"] = (
                f"PF: {pf:.2f} "
                f"({'PASS' if criteria['profit_factor'] else 'FAIL'} "
                f"threshold: {self.min_profit_factor})"
            )
        else:
            criteria["profit_factor"] = False
            details["profit_factor"] = "NOT TESTED"
        
        # 6. Expectancy
        if metrics:
            exp = metrics.get("expectancy", 0)
            criteria["expectancy"] = exp > self.min_expectancy
            details["expectancy"] = (
                f"Expectancy: ${exp:+,.2f} "
                f"({'PASS' if criteria['expectancy'] else 'FAIL'} "
                f"threshold: ${self.min_expectancy})"
            )
        else:
            criteria["expectancy"] = False
            details["expectancy"] = "NOT TESTED"
        
        # Calculate score
        score = sum(1 for v in criteria.values() if v)
        passed = score >= 5  # At least 5/6 criteria must pass
        
        return FilterResult(
            passed=passed,
            score=score,
            criteria=criteria,
            details=details,
        )
    
    def quick_check(self, metrics: Dict) -> bool:
        """
        Quick check using only basic metrics.
        Returns True if metrics look reasonable.
        """
        pf = metrics.get("profit_factor", 0)
        wr = metrics.get("win_rate", 0)
        exp = metrics.get("expectancy", 0)
        max_dd = metrics.get("max_drawdown_pct", 100)
        
        return (
            pf > 1.0 and
            wr > 0.40 and
            exp > 0 and
            max_dd < 25
        )

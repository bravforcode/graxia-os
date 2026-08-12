# DEPRECATED: Use core/risk/monte_carlo.py instead. Will be removed in Phase 5.
"""
Monte Carlo Simulator — Stress test strategy robustness

Runs N simulations of trade sequences to estimate:
- Probability of profit
- Max drawdown distribution
- Confidence intervals for returns
- p-value for strategy significance
"""

import math
import random
from dataclasses import dataclass
from typing import Literal


@dataclass
class MonteCarloResult:
    """Monte Carlo simulation result"""

    n_simulations: int
    n_trades: int

    # Profit probability
    prob_profit: float  # % of simulations that are profitable
    p_value: float  # Statistical significance

    # Return distribution
    median_return: float
    mean_return: float
    std_return: float
    ci_5th: float  # 5th percentile
    ci_95th: float  # 95th percentile

    # Drawdown distribution
    median_max_dd: float
    worst_max_dd: float
    ci_95_max_dd: float

    # Survival
    survival_rate: float  # % of sims with DD < 20%

    # Mode
    mode: Literal["bootstrap", "shuffle"] = "shuffle"

    # Details
    returns: list[float] = None
    max_drawdowns: list[float] = None

    def __post_init__(self):
        if self.returns is None:
            self.returns = []
        if self.max_drawdowns is None:
            self.max_drawdowns = []


def _t_test_p_value(returns: list[float]) -> float:
    """
    One-sample t-test: is mean return significantly different from 0?

    Uses scipy.stats.t for proper t-distribution CDF.
    Falls back to normal approximation if scipy unavailable.
    """
    n = len(returns)
    if n < 5:
        return 1.0

    mean = sum(returns) / n
    if mean == 0:
        return 1.0

    variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
    std = math.sqrt(variance)
    se = std / math.sqrt(n)

    t_stat = mean / se
    df = n - 1

    try:
        from scipy.stats import t as t_dist

        # Two-tailed p-value
        p_value = t_dist.sf(abs(t_stat), df) * 2
    except ImportError:
        # Fallback: normal approximation (accurate for df > 30)
        x = abs(t_stat)
        if x > 8:
            return 0.0
        p_value = math.erfc(x / math.sqrt(2))

    return min(1.0, max(0.0, p_value))


class MonteCarloSimulator:
    """
    Monte Carlo simulation for trading strategy validation.

    Usage:
        simulator = MonteCarloSimulator()
        result = simulator.run(trades, n_simulations=10000)

        # Check if strategy is robust
        if result.p_value > 0.95 and result.survival_rate > 0.9:
            print("Strategy is robust!")
    """

    def __init__(self, seed: int | None = None):
        self.seed = seed

    def run(
        self,
        trades: list[dict],
        n_simulations: int = 10000,
        initial_capital: float = 10000.0,
        risk_per_trade_pct: float = 1.0,
        max_drawdown_pct: float = 20.0,
        mode: Literal["bootstrap", "shuffle"] = "shuffle",
    ) -> MonteCarloResult:
        """
        Run Monte Carlo simulation.

        Modes:
            - "shuffle": random permutation of trades (tests path dependency — whether trade order matters)
            - "bootstrap": sample with replacement (tests distribution of outcomes — more conservative)

        Args:
            trades: List of trade dicts with 'pnl' or 'return_pct'
            n_simulations: Number of simulations
            initial_capital: Starting capital
            risk_per_trade_pct: Risk per trade
            max_drawdown_pct: Max drawdown threshold
            mode: "shuffle" for path dependency, "bootstrap" for outcome distribution

        Returns:
            MonteCarloResult with statistics
        """
        if not trades:
            return self._empty_result(n_simulations, mode)

        # Extract returns
        returns = []
        for trade in trades:
            if "return_pct" in trade:
                returns.append(trade["return_pct"] / 100)
            elif "pnl" in trade and "entry_price" in trade:
                ret = trade["pnl"] / (trade["entry_price"] * trade.get("quantity", 1))
                returns.append(ret)
            elif "pnl" in trade:
                returns.append(trade["pnl"] / initial_capital)

        if not returns:
            return self._empty_result(n_simulations)

        # Run simulations
        random.seed(self.seed)

        sim_returns = []
        sim_max_dds = []

        for _ in range(n_simulations):
            if mode == "bootstrap":
                shuffled = random.choices(returns, k=len(returns))
            else:
                shuffled = random.sample(returns, k=len(returns))

            # Calculate equity curve
            equity = initial_capital
            peak = equity
            max_dd = 0

            for ret in shuffled:
                equity *= 1 + ret
                if equity > peak:
                    peak = equity
                dd = (peak - equity) / peak
                if dd > max_dd:
                    max_dd = dd

            total_return = (equity - initial_capital) / initial_capital
            sim_returns.append(total_return)
            sim_max_dds.append(max_dd)

        # Sort for percentiles
        sim_returns.sort()
        sim_max_dds.sort()

        n = len(sim_returns)

        # Calculate statistics
        prob_profit = sum(1 for r in sim_returns if r > 0) / n

        # p-value via one-sample t-test on trade returns
        p_value = _t_test_p_value(returns)

        median_return = sim_returns[n // 2]
        mean_return = sum(sim_returns) / n
        std_return = math.sqrt(sum((r - mean_return) ** 2 for r in sim_returns) / n)

        ci_5th = sim_returns[int(n * 0.05)]
        ci_95th = sim_returns[int(n * 0.95)]

        median_max_dd = sim_max_dds[n // 2]
        worst_max_dd = sim_max_dds[-1]
        ci_95_max_dd = sim_max_dds[int(n * 0.95)]

        survival_rate = sum(1 for dd in sim_max_dds if dd < max_drawdown_pct / 100) / n

        return MonteCarloResult(
            n_simulations=n_simulations,
            n_trades=len(returns),
            prob_profit=prob_profit,
            p_value=p_value,
            median_return=median_return,
            mean_return=mean_return,
            std_return=std_return,
            ci_5th=ci_5th,
            ci_95th=ci_95th,
            median_max_dd=median_max_dd,
            worst_max_dd=worst_max_dd,
            ci_95_max_dd=ci_95_max_dd,
            survival_rate=survival_rate,
            mode=mode,
            returns=sim_returns,
            max_drawdowns=sim_max_dds,
        )

    def _empty_result(self, n_simulations: int, mode: Literal["bootstrap", "shuffle"] = "shuffle") -> MonteCarloResult:
        """Return empty result for no trades"""
        return MonteCarloResult(
            n_simulations=n_simulations,
            n_trades=0,
            prob_profit=0.0,
            p_value=0.0,
            median_return=0.0,
            mean_return=0.0,
            std_return=0.0,
            ci_5th=0.0,
            ci_95th=0.0,
            median_max_dd=0.0,
            worst_max_dd=0.0,
            ci_95_max_dd=0.0,
            survival_rate=0.0,
            mode=mode,
        )

    def validate_strategy(self, result: MonteCarloResult) -> dict[str, bool]:
        """
        Validate strategy against robustness criteria.

        p_value from t-test: LOW p-value = strategy IS significant.
        - p_value < 0.05: reject H0 (mean return = 0) → strategy has edge
        - p_value > 0.05: fail to reject H0 → no significant edge

        Criteria:
        - p_value < 0.05 (statistically significant)
        - Survival rate > 0.90 (DD < 20%)
        - Median return > 0
        """
        return {
            "p_value_pass": result.p_value < 0.05,
            "survival_pass": result.survival_rate > 0.90,
            "median_return_pass": result.median_return > 0,
            "all_pass": (result.p_value < 0.05 and result.survival_rate > 0.90 and result.median_return > 0),
        }

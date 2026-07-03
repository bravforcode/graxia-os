"""Phase 4 — Return Decomposition.

Decomposes strategy returns into alpha, beta, and carry components.
Based on AQR (2020-2025) research on return attribution.

Components:
- Alpha: excess return not explained by market exposure or carry
- Beta: return from market exposure (directional bets)
- Carry: return from swap/rollover differentials
- Cost: transaction costs (spread, slippage, commission)

Research:
- AQR: "Unintentional risks can be a large part of a portfolio's total active risk"
- TSM strategy has meaningful carry component (swap differentials across 8 assets)
- Beta component (vol-targeted market exposure) conflated with alpha
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class DecompositionConfig:
    """Return decomposition configuration."""

    # Market benchmark for beta calculation
    benchmark_return: float = 0.0  # Daily benchmark return
    risk_free_rate: float = 0.0  # Daily risk-free rate

    # Carry estimation
    annual_trading_days: int = 24192  # M15 bars per year
    swap_cost_per_bar: float = 0.0  # Average swap cost per bar

    # Regression window
    regression_window: int = 252  # Bars for rolling regression


@dataclass
class ReturnDecomposition:
    """Decomposed return components."""

    total_return: float = 0.0
    alpha: float = 0.0  # Excess return not from beta or carry
    beta_return: float = 0.0  # Return from market exposure
    carry_return: float = 0.0  # Return from swap/rollover
    cost_return: float = 0.0  # Transaction costs
    residual: float = 0.0  # Unexplained portion

    # Metrics
    beta: float = 0.0  # Market beta
    alpha_annual: float = 0.0  # Annualized alpha
    information_ratio: float = 0.0  # Alpha / tracking error
    r_squared: float = 0.0  # How much variance is explained


class ReturnDecomposer:
    """Decomposes strategy returns into alpha, beta, and carry.

    Uses rolling regression to estimate beta exposure and attributes
    remaining returns to alpha, carry, and costs.
    """

    def __init__(self, config: DecompositionConfig | None = None):
        self.config = config or DecompositionConfig()
        self._strategy_returns: list[float] = []
        self._benchmark_returns: list[float] = []
        self._carry_returns: list[float] = []
        self._cost_returns: list[float] = []

    def update(
        self,
        strategy_return: float,
        benchmark_return: float | None = None,
        carry_return: float = 0.0,
        cost_return: float = 0.0,
    ):
        """Update with new return data.

        Args:
            strategy_return: Total strategy return for the bar
            benchmark_return: Market benchmark return (optional)
            carry_return: Swap/rollover return component
            cost_return: Transaction cost component
        """
        self._strategy_returns.append(strategy_return)
        self._benchmark_returns.append(benchmark_return or self.config.benchmark_return)
        self._carry_returns.append(carry_return)
        self._cost_returns.append(cost_return)

    def decompose(self, window: int | None = None) -> ReturnDecomposition:
        """Decompose returns into components.

        Args:
            window: Number of bars for regression (default: config.regression_window)

        Returns:
            ReturnDecomposition with all components
        """
        w = window or self.config.regression_window
        n = min(w, len(self._strategy_returns))

        if n < 10:
            return ReturnDecomposition()

        strat = self._strategy_returns[-n:]
        bench = self._benchmark_returns[-n:]
        carry = self._carry_returns[-n:]
        costs = self._cost_returns[-n:]

        # Total return
        total_return = sum(strat)

        # Beta estimation via OLS regression
        beta, alpha, r_squared = self._estimate_beta(strat, bench)

        # Beta return = beta * benchmark return
        beta_return = sum(beta * b for b in bench)

        # Carry return
        carry_return = sum(carry)

        # Cost return (negative)
        cost_return = sum(costs)

        # Alpha = total - beta_return - carry_return - cost_return
        alpha = total_return - beta_return - carry_return - cost_return

        # Residual (should be ~0 if decomposition is complete)
        residual = 0.0

        # Annualize alpha
        alpha_per_bar = alpha / n if n > 0 else 0
        alpha_annual = alpha_per_bar * self.config.annual_trading_days

        # Information ratio
        tracking_error = self._tracking_error(strat, bench, beta)
        information_ratio = (alpha_annual / tracking_error) if tracking_error > 0 else 0.0

        return ReturnDecomposition(
            total_return=total_return,
            alpha=alpha,
            beta_return=beta_return,
            carry_return=carry_return,
            cost_return=cost_return,
            residual=residual,
            beta=beta,
            alpha_annual=alpha_annual,
            information_ratio=information_ratio,
            r_squared=r_squared,
        )

    def _estimate_beta(self, strategy: list[float], benchmark: list[float]) -> tuple[float, float, float]:
        """Estimate beta via OLS regression.

        Returns:
            (beta, alpha, r_squared)
        """
        n = len(strategy)
        if n < 10:
            return 0.0, 0.0, 0.0

        mean_s = sum(strategy) / n
        mean_b = sum(benchmark) / n

        cov = sum((strategy[i] - mean_s) * (benchmark[i] - mean_b) for i in range(n)) / (n - 1)
        var_b = sum((b - mean_b) ** 2 for b in benchmark) / (n - 1)

        if var_b <= 0:
            return 0.0, 0.0, 0.0

        beta = cov / var_b
        alpha = mean_s - beta * mean_b

        # R-squared
        ss_res = sum((strategy[i] - (alpha + beta * benchmark[i])) ** 2 for i in range(n))
        ss_tot = sum((s - mean_s) ** 2 for s in strategy)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        return beta, alpha, r_squared

    def _tracking_error(self, strategy: list[float], benchmark: list[float], beta: float) -> float:
        """Calculate annualized tracking error."""
        residuals = [strategy[i] - beta * benchmark[i] for i in range(len(strategy))]
        n = len(residuals)
        if n < 2:
            return 0.0
        mean_r = sum(residuals) / n
        var_r = sum((r - mean_r) ** 2 for r in residuals) / (n - 1)
        return math.sqrt(var_r * self.config.annual_trading_days)

    def reset(self):
        """Reset state."""
        self._strategy_returns.clear()
        self._benchmark_returns.clear()
        self._carry_returns.clear()
        self._cost_returns.clear()

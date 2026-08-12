"""Phase 3 — Cost Sensitivity Sweep.

Tests strategy profitability across multiple cost assumptions to validate
robustness. Strategy must be profitable at realistic costs (15 bps) to pass.

Industry standard from research:
- 5 bps: optimistic (institutional DMA)
- 15 bps: realistic (retail ECN)
- 30 bps: stressed (news events, low liquidity)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CostSensitivityResult:
    """Result of cost sensitivity sweep."""

    costs_tested: list[float]  # bps levels tested
    profitable_at: list[bool]  # profitable at each cost level
    breakeven_cost: float  # estimated breakeven cost in bps
    passes_robustness: bool  # profitable at >= 15 bps (realistic)
    passes_stress: bool  # profitable at >= 30 bps (stressed)
    sharpe_at_realistic: float  # Sharpe at 15 bps (realistic cost)


def estimate_breakeven_cost(
    returns_before_costs: list[float],
    cost_bps_range: list[float] | None = None,
    n_trades_per_period: float = 1.0,
) -> CostSensitivityResult:
    """Estimate breakeven transaction cost level.

    Args:
        returns_before_costs: Per-bar returns before transaction costs
        cost_bps_range: List of cost levels in bps to test (default: [0, 5, 10, 15, 20, 30, 50])
        n_trades_per_period: Average number of trades per bar (for cost scaling)

    Returns:
        CostSensitivityResult with profitability at each cost level
    """
    if cost_bps_range is None:
        cost_bps_range = [0, 5, 10, 15, 20, 30, 50]

    if not returns_before_costs or len(returns_before_costs) < 10:
        return CostSensitivityResult(
            costs_tested=cost_bps_range,
            profitable_at=[False] * len(cost_bps_range),
            breakeven_cost=0.0,
            passes_robustness=False,
            passes_stress=False,
            sharpe_at_realistic=0.0,
        )

    total_return_before = sum(returns_before_costs)
    n_bars = len(returns_before_costs)

    profitable_at = []
    sharpe_at_realistic = 0.0

    for cost_bps in cost_bps_range:
        # Total cost = cost_per_trade * trades_per_bar * n_bars
        cost_per_bar = (cost_bps / 10000) * n_trades_per_period
        total_cost = cost_per_bar * n_bars
        net_return = total_return_before - total_cost
        profitable_at.append(net_return > 0)

        # Sharpe at realistic cost (15 bps)
        if cost_bps == 15:
            net_returns = [r - cost_per_bar for r in returns_before_costs]
            mean_r = sum(net_returns) / len(net_returns)
            var_r = sum((r - mean_r) ** 2 for r in net_returns) / (len(net_returns) - 1)
            std_r = var_r**0.5
            sharpe_at_realistic = (mean_r / std_r * (24192**0.5)) if std_r > 0 else 0.0

    # Find breakeven cost
    breakeven_cost = 0.0
    for i, (cost, prof) in enumerate(zip(cost_bps_range, profitable_at)):
        if not prof and i > 0:
            # Interpolate between last profitable and first unprofitable
            breakeven_cost = cost_bps_range[i - 1]
            break
        elif not prof and i == 0:
            breakeven_cost = 0.0
            break
    else:
        breakeven_cost = cost_bps_range[-1]  # Profitable at all levels

    # Determine pass/fail
    realistic_idx = cost_bps_range.index(15) if 15 in cost_bps_range else -1
    stress_idx = cost_bps_range.index(30) if 30 in cost_bps_range else -1

    passes_robustness = profitable_at[realistic_idx] if realistic_idx >= 0 else False
    passes_stress = profitable_at[stress_idx] if stress_idx >= 0 else False

    return CostSensitivityResult(
        costs_tested=cost_bps_range,
        profitable_at=profitable_at,
        breakeven_cost=breakeven_cost,
        passes_robustness=passes_robustness,
        passes_stress=passes_stress,
        sharpe_at_realistic=sharpe_at_realistic,
    )

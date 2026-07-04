"""Phase 3 — Transaction Cost Analysis (TCA) Metrics.

Institutional-grade TCA metrics for measuring execution quality.
Based on LMAX (2020) and GFXC (2020) standards.

Core metrics:
- Fill Ratio: fraction of orders successfully filled
- Price Variation: slippage + price improvement
- Implementation Shortfall: difference between decision price and execution price
- Market Impact: price movement caused by the order
- Execution Cost: total cost including spread, slippage, and market impact
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class TCAMetrics:
    """Transaction Cost Analysis metrics for a single trade or aggregate."""

    # Core TCA metrics
    arrival_price: Decimal = Decimal("0")  # Price at decision time
    execution_price: Decimal = Decimal("0")  # Actual fill price
    slippage_bps: float = 0.0  # (execution - arrival) / arrival * 10000
    implementation_shortfall_bps: float = 0.0  # Decision cost in bps
    market_impact_bps: float = 0.0  # Price movement caused by order

    # Execution quality
    fill_ratio: float = 1.0  # Filled / Requested
    adverse_selection_bps: float = 0.0  # Cost from adverse selection

    # Cost breakdown
    spread_cost_bps: float = 0.0  # Half-spread paid
    commission_bps: float = 0.0  # Commission in bps
    total_execution_cost_bps: float = 0.0  # All-in cost in bps

    # Direction
    side: str = ""  # BUY or SELL
    symbol: str = ""
    volume: float = 0.0
    bar_index: int = 0


def calculate_tca(
    arrival_price: Decimal,
    execution_price: Decimal,
    side: str,
    spread_bps: float = 0.0,
    commission_bps: float = 0.0,
    market_impact_bps: float = 0.0,
    adverse_selection_bps: float = 0.0,
    fill_ratio: float = 1.0,
    symbol: str = "",
    volume: float = 0.0,
    bar_index: int = 0,
) -> TCAMetrics:
    """Calculate TCA metrics for a single fill.

    Args:
        arrival_price: Price when decision was made
        execution_price: Actual fill price
        side: "BUY" or "SELL"
        spread_bps: Half-spread cost in bps
        commission_bps: Commission in bps
        market_impact_bps: Estimated market impact in bps
        adverse_selection_bps: Adverse selection cost in bps
        fill_ratio: Fraction of order filled
        symbol: Trading symbol
        volume: Order volume
        bar_index: Bar index at execution

    Returns:
        TCAMetrics with computed metrics
    """
    arr = float(arrival_price)
    exe = float(execution_price)

    if arr <= 0 or side not in ("BUY", "SELL"):
        return TCAMetrics()

    # Price variation (slippage from arrival)
    if side == "BUY":
        slippage_bps = ((exe - arr) / arr) * 10000
    else:
        slippage_bps = ((arr - exe) / arr) * 10000

    # Implementation shortfall
    implementation_shortfall_bps = slippage_bps

    # Total execution cost
    total_cost = slippage_bps + spread_bps + commission_bps + market_impact_bps + adverse_selection_bps

    return TCAMetrics(
        arrival_price=arrival_price,
        execution_price=execution_price,
        slippage_bps=round(slippage_bps, 4),
        implementation_shortfall_bps=round(implementation_shortfall_bps, 4),
        market_impact_bps=market_impact_bps,
        fill_ratio=fill_ratio,
        adverse_selection_bps=adverse_selection_bps,
        spread_cost_bps=spread_bps,
        commission_bps=commission_bps,
        total_execution_cost_bps=round(total_cost, 4),
        side=side,
        symbol=symbol,
        volume=volume,
        bar_index=bar_index,
    )


def calculate_portfolio_tca(trades: list[TCAMetrics]) -> dict:
    """Calculate aggregate TCA metrics for a portfolio of trades.

    Args:
        trades: List of TCAMetrics from individual fills

    Returns:
        Dict with aggregate TCA metrics
    """
    if not trades:
        return {
            "total_trades": 0,
            "avg_slippage_bps": 0.0,
            "avg_market_impact_bps": 0.0,
            "avg_total_cost_bps": 0.0,
            "avg_fill_ratio": 0.0,
            "total_cost_usd": 0.0,
        }

    n = len(trades)
    total_slippage = sum(t.slippage_bps for t in trades)
    total_impact = sum(t.market_impact_bps for t in trades)
    total_cost = sum(t.total_execution_cost_bps for t in trades)
    total_fill_ratio = sum(t.fill_ratio for t in trades)

    return {
        "total_trades": n,
        "avg_slippage_bps": total_slippage / n,
        "avg_market_impact_bps": total_impact / n,
        "avg_total_cost_bps": total_cost / n,
        "avg_fill_ratio": total_fill_ratio / n,
        "worst_slippage_bps": max(t.slippage_bps for t in trades),
        "best_slippage_bps": min(t.slippage_bps for t in trades),
    }

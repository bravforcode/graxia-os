"""Phase 3 — Portfolio Heat Monitoring.

Tracks total risk across all open positions and enforces hard limits.
Professional rule: total portfolio heat should not exceed 5-10% of account.

Based on research:
- March 2020: 99% VaR breached on 12 consecutive days
- Diversification fails when most needed (correlations spike)
- Total heat = sum of (entry - stop_loss) * size across all positions
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class PortfolioHeatMetrics:
    """Portfolio heat metrics."""

    total_heat_usd: Decimal = Decimal("0")  # Total dollar risk if all stops hit
    heat_pct: float = 0.0  # Heat as % of equity
    position_count: int = 0
    max_heat_pct: float = 10.0  # Hard limit
    breached: bool = False
    positions_at_risk: list[str] = None  # Symbol list

    def __post_init__(self):
        if self.positions_at_risk is None:
            self.positions_at_risk = []


def calculate_portfolio_heat(
    positions: list[dict],
    account_equity: Decimal,
    max_heat_pct: float = 8.0,
) -> PortfolioHeatMetrics:
    """Calculate total portfolio heat.

    Args:
        positions: List of position dicts with keys:
            - symbol: str
            - entry_price: Decimal
            - stop_loss: Decimal
            - quantity: Decimal
            - side: str ("LONG" or "SHORT")
        account_equity: Current account equity
        max_heat_pct: Maximum allowed heat as % of equity

    Returns:
        PortfolioHeatMetrics with current heat analysis
    """
    total_heat = Decimal("0")
    positions_at_risk = []

    for pos in positions:
        entry = pos.get("entry_price", Decimal("0"))
        stop = pos.get("stop_loss", Decimal("0"))
        qty = pos.get("quantity", Decimal("0"))
        side = pos.get("side", "LONG")
        symbol = pos.get("symbol", "")

        if entry <= 0 or stop <= 0 or qty <= 0:
            continue

        if side == "LONG":
            risk_per_unit = entry - stop  # Entry - stop (stop below entry)
        else:
            risk_per_unit = stop - entry  # Stop - entry (stop above entry)

        if risk_per_unit <= 0:
            continue

        position_heat = risk_per_unit * qty
        total_heat += position_heat

        # Track positions contributing > 2% individually
        if account_equity > 0:
            pos_heat_pct = float(position_heat / account_equity * 100)
            if pos_heat_pct > 2.0:
                positions_at_risk.append(symbol)

    # Calculate heat percentage
    heat_pct = float(total_heat / account_equity * 100) if account_equity > 0 else 0.0
    breached = heat_pct > max_heat_pct

    return PortfolioHeatMetrics(
        total_heat_usd=total_heat,
        heat_pct=round(heat_pct, 2),
        position_count=len(positions),
        max_heat_pct=max_heat_pct,
        breached=breached,
        positions_at_risk=positions_at_risk,
    )


def correlation_adjusted_heat(
    base_heat_pct: float,
    avg_correlation: float,
    max_heat_pct: float = 8.0,
) -> float:
    """Adjust heat estimate for correlation between positions.

    During normal markets (corr ~0.3): heat is as calculated.
    During crises (corr ~0.8): diversification benefit disappears.

    Args:
        base_heat_pct: Base heat percentage
        avg_correlation: Average pairwise correlation between positions
        max_heat_pct: Maximum allowed heat

    Returns:
        Adjusted heat percentage
    """
    # Correlation multiplier: 1.0 at corr=0, up to 2.0 at corr=1.0
    corr_mult = 1.0 + avg_correlation
    adjusted = base_heat_pct * corr_mult
    return min(adjusted, max_heat_pct * 1.5)  # Cap at 150% of limit

"""Capacity ceiling analysis — at what position size does slippage erode the edge?"""

def compute_capacity_ceiling(
    avg_gross_per_trade: float = 0.21,
    base_slippage_pips: float = 0.3,
    pip_value_per_lot: float = 10.0,
    contract_size: float = 100,
) -> dict:
    """Compute max position size before edge is consumed by slippage."""
    # Edge per unit
    edge_per_unit = avg_gross_per_trade / contract_size  # $/unit

    # Slippage cost per unit at different order sizes
    results = {}
    for lots in [0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0]:
        # Slippage multiplier by size category
        if lots < 0.1:
            mult = 0.5
        elif lots < 0.5:
            mult = 1.0
        elif lots < 2.0:
            mult = 1.5
        elif lots < 5.0:
            mult = 2.5
        else:
            mult = 4.0

        slippage_cost = base_slippage_pips * mult * pip_value_per_lot * lots
        net_edge = avg_gross_per_trade * lots / (contract_size * lots / contract_size) - slippage_cost

        results[f"{lots} lots"] = {
            "slippage_cost": round(slippage_cost, 4),
            "net_edge": round(avg_gross_per_trade - slippage_cost, 4),
            "edge_erosion_pct": round((slippage_cost / avg_gross_per_trade) * 100, 1) if avg_gross_per_trade > 0 else 0,
        }

    # Find ceiling (where net edge = 0)
    ceiling_lots = 0.01
    for lots_10x in range(1, 100):
        lots = lots_10x / 10.0
        if lots < 0.1:
            mult = 0.5
        elif lots < 0.5:
            mult = 1.0
        elif lots < 2.0:
            mult = 1.5
        elif lots < 5.0:
            mult = 2.5
        else:
            mult = 4.0
        slippage_cost = base_slippage_pips * mult * pip_value_per_lot * lots
        if slippage_cost >= avg_gross_per_trade:
            ceiling_lots = (lots_10x - 1) / 10.0
            break

    return {
        "avg_gross_per_trade": avg_gross_per_trade,
        "ceiling_lots": ceiling_lots,
        "analysis": results,
    }

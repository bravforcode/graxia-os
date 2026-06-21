"""
Trade cost model for backtesting.

Standard cost scenarios per Section 9.6 of the Master Plan.
"""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class CostScenario:
    name: str
    spread_multiplier: float  # 1.0 = base, 1.5 = stress1, etc.
    slippage_multiplier: float
    commission_per_lot: Decimal
    description: str


# Standard cost scenarios per Section 9.6
BASE = CostScenario("base", 1.0, 1.0, Decimal("3.5"), "baseline")
STRESS_1 = CostScenario("stress_1", 1.5, 1.5, Decimal("3.5"), "moderate stress")
STRESS_2 = CostScenario("stress_2", 2.0, 2.0, Decimal("3.5"), "adverse ordinary")
STRESS_3 = CostScenario("stress_3", 3.0, 3.0, Decimal("3.5"), "severe condition")

GAP_SCENARIO = CostScenario("gap", 5.0, 3.0, Decimal("3.5"), "weekend/news gap")
EVENT_BLOCK = CostScenario("event_block", 0, 0, Decimal("0"), "no trade during event")

ALL_SCENARIOS = [BASE, STRESS_1, STRESS_2, STRESS_3, GAP_SCENARIO]


@dataclass
class TradeCosts:
    spread_cost: Decimal
    slippage_cost: Decimal
    commission: Decimal
    swap: Decimal
    total: Decimal


def calculate_trade_costs(
    entry_price: Decimal,
    exit_price: Decimal,
    volume: Decimal,  # lots
    contract_size: Decimal,
    spread_points: Decimal,
    scenario: CostScenario,
    commission_per_lot: Decimal | None = None,
) -> TradeCosts:
    """Calculate total trade costs for a given scenario."""
    effective_spread = spread_points * Decimal(str(scenario.spread_multiplier))
    effective_slippage_mult = Decimal(str(scenario.slippage_multiplier))

    spread_cost = effective_spread * contract_size * volume
    slippage_cost = (abs(exit_price - entry_price) * effective_slippage_mult
                     if effective_slippage_mult != 1 else Decimal("0"))
    comm = commission_per_lot if commission_per_lot is not None else scenario.commission_per_lot
    commission = comm * volume
    swap = Decimal("0")  # ponytail: swap not modelled here, add when carry logic needed
    total = spread_cost + slippage_cost + commission + swap

    return TradeCosts(
        spread_cost=spread_cost,
        slippage_cost=slippage_cost,
        commission=commission,
        swap=swap,
        total=total,
    )


def run_cost_stress_matrix(
    entry_price: Decimal,
    exit_price: Decimal,
    volume: Decimal,
    contract_size: Decimal,
    spread_points: Decimal,
    commission_per_lot: Decimal | None = None,
) -> list[TradeCosts]:
    """Run all cost scenarios and return results."""
    return [
        calculate_trade_costs(entry_price, exit_price, volume, contract_size,
                              spread_points, s, commission_per_lot)
        for s in ALL_SCENARIOS
    ]

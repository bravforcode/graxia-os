"""Cost model — spread x slippage x commission stress matrix."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class CostScenario:
    name: str
    spread_mult: Decimal
    slippage_mult: Decimal
    commission_mult: Decimal


BASE = CostScenario("base", Decimal("1"), Decimal("1"), Decimal("1"))
STRESS_1 = CostScenario("stress_1", Decimal("1.5"), Decimal("1.5"), Decimal("1"))
STRESS_2 = CostScenario("stress_2", Decimal("2"), Decimal("2"), Decimal("1"))
STRESS_3 = CostScenario("stress_3", Decimal("3"), Decimal("3"), Decimal("1"))

ALL_SCENARIOS = [BASE, STRESS_1, STRESS_2, STRESS_3]


@dataclass(frozen=True)
class TradeCosts:
    scenario: str
    spread_cost: Decimal
    slippage_cost: Decimal
    commission: Decimal
    total_cost: Decimal


def calculate_trade_costs(
    entry_price: Decimal,
    exit_price: Decimal,
    volume: Decimal,
    contract_size: Decimal,
    spread_points: Decimal,
    scenario: CostScenario,
    commission_per_lot: Decimal | None = None,
    slippage_points: Decimal | None = None,
) -> TradeCosts:
    comm = commission_per_lot or Decimal("0")
    # Coerce any float inputs to Decimal for safe multiplication
    comm = Decimal(str(comm)) if not isinstance(comm, Decimal) else comm
    volume = Decimal(str(volume)) if not isinstance(volume, Decimal) else volume
    contract_size = Decimal(str(contract_size)) if not isinstance(contract_size, Decimal) else contract_size
    spread_points = Decimal(str(spread_points)) if not isinstance(spread_points, Decimal) else spread_points
    # Slippage defaults to 30% of spread if not provided (realistic for liquid instruments)
    slip_pts = slippage_points if slippage_points is not None else spread_points * Decimal("0.3")
    slip_pts = Decimal(str(slip_pts)) if not isinstance(slip_pts, Decimal) else slip_pts
    spread = spread_points * scenario.spread_mult * contract_size * volume
    slippage = slip_pts * scenario.slippage_mult * contract_size * volume
    commission = comm * scenario.commission_mult * volume
    return TradeCosts(
        scenario=scenario.name,
        spread_cost=spread,
        slippage_cost=slippage,
        commission=commission,
        total_cost=spread + slippage + commission,
    )


def run_cost_stress_matrix(
    entry_price: Decimal,
    exit_price: Decimal,
    volume: Decimal,
    contract_size: Decimal,
    spread_points: Decimal,
    commission_per_lot: Decimal | None = None,
    slippage_points: Decimal | None = None,
) -> list[TradeCosts]:
    return [
        calculate_trade_costs(
            entry_price,
            exit_price,
            volume,
            contract_size,
            spread_points,
            s,
            commission_per_lot,
            slippage_points,
        )
        for s in ALL_SCENARIOS
    ]

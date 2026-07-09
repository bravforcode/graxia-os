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
    """Calculate trade costs with separate spread and slippage components.

    Args:
        entry_price: Entry price.
        exit_price: Exit price.
        volume: Trade volume in lots.
        contract_size: Contract size per lot.
        spread_points: Spread in price points.
        scenario: Cost scenario (base, stress_1, etc.).
        commission_per_lot: Commission per lot (optional).
        slippage_points: Slippage in price points (optional, defaults to spread_points).

    Returns:
        TradeCosts with separate spread, slippage, and commission components.
    """
    comm = commission_per_lot or Decimal("0")
    # Coerce any float inputs to Decimal for safe multiplication
    comm = Decimal(str(comm)) if not isinstance(comm, Decimal) else comm
    volume = Decimal(str(volume)) if not isinstance(volume, Decimal) else volume
    contract_size = Decimal(str(contract_size)) if not isinstance(contract_size, Decimal) else contract_size
    spread_points = Decimal(str(spread_points)) if not isinstance(spread_points, Decimal) else spread_points

    # Use separate slippage if provided, otherwise fall back to spread_points
    # (backward compatible: slippage = spread when slippage_points not specified)
    if slippage_points is not None:
        slippage_points = Decimal(str(slippage_points)) if not isinstance(slippage_points, Decimal) else slippage_points
    else:
        slippage_points = spread_points

    spread = spread_points * scenario.spread_mult * contract_size * volume
    slippage = slippage_points * scenario.slippage_mult * contract_size * volume
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
    """Run cost stress matrix with separate spread and slippage components.

    Args:
        entry_price: Entry price.
        exit_price: Exit price.
        volume: Trade volume in lots.
        contract_size: Contract size per lot.
        spread_points: Spread in price points.
        commission_per_lot: Commission per lot (optional).
        slippage_points: Slippage in price points (optional, defaults to spread_points).

    Returns:
        List of TradeCosts for each scenario.
    """
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

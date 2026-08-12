from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True)
class CostScenario:
    name: str
    spread_multiplier: Decimal
    slippage_multiplier: Decimal
    commission_multiplier: Decimal

    @property
    def label(self) -> str:
        return self.name

# Standard cost scenarios per master plan
BASE = CostScenario("base", Decimal("1.0"), Decimal("1.0"), Decimal("1.0"))
STRESS_1 = CostScenario("stress_1", Decimal("1.5"), Decimal("1.5"), Decimal("1.5"))
STRESS_2 = CostScenario("stress_2", Decimal("2.0"), Decimal("2.0"), Decimal("2.0"))
STRESS_3 = CostScenario("stress_3", Decimal("3.0"), Decimal("3.0"), Decimal("3.0"))

ALL_SCENARIOS = [BASE, STRESS_1, STRESS_2, STRESS_3]

def get_scenario(name: str) -> CostScenario:
    for s in ALL_SCENARIOS:
        if s.name == name:
            return s
    raise ValueError(f"Unknown scenario: {name}")

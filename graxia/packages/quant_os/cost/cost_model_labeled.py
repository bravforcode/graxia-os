"""Phase BE-P4 — Cost model with evidence quality labels."""
from dataclasses import dataclass
from enum import Enum


class EvidenceLevel(Enum):
    ASSUMED_STRESS = "ASSUMED_STRESS"  # Pre-committed conservative
    QUOTE_OBSERVED = "QUOTE_OBSERVED"  # From tick capture
    DEMO_OBSERVED = "DEMO_OBSERVED"    # From demo fills
    LIVE_OBSERVED = "LIVE_OBSERVED"    # From micro-live fills


@dataclass
class LabeledCost:
    spread_points: float
    slippage_points: float
    commission_per_lot: float
    swap_long_points: float
    swap_short_points: float
    evidence_level: str  # EvidenceLevel value
    quality_note: str = ""

    @property
    def total_cost_points(self) -> float:
        return self.spread_points + self.slippage_points

    def to_dict(self) -> dict:
        return {
            "spread_points": self.spread_points,
            "slippage_points": self.slippage_points,
            "commission_per_lot": self.commission_per_lot,
            "swap_long_points": self.swap_long_points,
            "swap_short_points": self.swap_short_points,
            "evidence_level": self.evidence_level,
            "quality_note": self.quality_note,
            "total_cost_points": self.total_cost_points,
        }


class LabeledCostModel:
    """Cost model with evidence quality tracking."""

    def __init__(self):
        self._scenarios: dict[str, LabeledCost] = {}

    def add_scenario(self, name: str, cost: LabeledCost) -> None:
        self._scenarios[name] = cost

    def get_scenario(self, name: str) -> LabeledCost | None:
        return self._scenarios.get(name)

    def get_all_scenarios(self) -> dict[str, LabeledCost]:
        return self._scenarios.copy()

    def stress_matrix(self) -> list[dict]:
        """Generate stress matrix from scenarios."""
        return [{"name": k, **v.to_dict()} for k, v in self._scenarios.items()]

    @classmethod
    def default_pre_demo(cls) -> "LabeledCostModel":
        """Default pre-demo model with ASSUMED_STRESS assumptions."""
        model = cls()
        model.add_scenario("base", LabeledCost(
            spread_points=3.0, slippage_points=0.5,
            commission_per_lot=7.0, swap_long_points=-2.5,
            swap_short_points=0.5,
            evidence_level=EvidenceLevel.ASSUMED_STRESS.value,
            quality_note="pre-demo conservative assumption",
        ))
        model.add_scenario("stress_1", LabeledCost(
            spread_points=4.5, slippage_points=0.75,
            commission_per_lot=7.0, swap_long_points=-2.5,
            swap_short_points=0.5,
            evidence_level=EvidenceLevel.ASSUMED_STRESS.value,
            quality_note="1.5x spread stress",
        ))
        model.add_scenario("stress_2", LabeledCost(
            spread_points=6.0, slippage_points=1.0,
            commission_per_lot=7.0, swap_long_points=-5.0,
            swap_short_points=1.0,
            evidence_level=EvidenceLevel.ASSUMED_STRESS.value,
            quality_note="2.0x spread + adverse swap",
        ))
        model.add_scenario("stress_3", LabeledCost(
            spread_points=9.0, slippage_points=1.5,
            commission_per_lot=7.0, swap_long_points=-7.5,
            swap_short_points=1.5,
            evidence_level=EvidenceLevel.ASSUMED_STRESS.value,
            quality_note="3.0x spread + severe gap",
        ))
        return model

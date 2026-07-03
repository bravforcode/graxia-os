"""Phase BE-P4 — Cost stress analyzer."""
from dataclasses import dataclass


@dataclass
class StressResult:
    scenario_name: str
    spread_multiplier: float
    total_cost_before: float
    total_cost_after: float
    cost_increase_pct: float
    sensitivity: str  # LOW, MEDIUM, HIGH


class CostStressAnalyzer:
    """Analyze strategy sensitivity to cost changes."""

    def __init__(self, base_cost: float = 3.5):
        self._base_cost = base_cost
        self._scenarios: list[dict] = []

    def add_scenario(self, name: str, spread_mult: float,
                     slippage_mult: float = 1.0) -> None:
        self._scenarios.append({
            "name": name,
            "spread_mult": spread_mult,
            "slippage_mult": slippage_mult,
        })

    def analyze(self, strategy_pnl_per_trade: float = 0.0) -> list[StressResult]:
        """Analyze sensitivity for each scenario."""
        results = []
        for sc in self._scenarios:
            base_spread = self._base_cost * 0.857  # ~3.0/3.5
            base_slippage = self._base_cost * 0.143  # ~0.5/3.5

            cost_before = self._base_cost
            cost_after = (base_spread * sc["spread_mult"] +
                         base_slippage * sc["slippage_mult"])

            increase_pct = ((cost_after - cost_before) / cost_before * 100
                          if cost_before > 0 else 0)

            # Sensitivity based on how much cost eats into edge
            if strategy_pnl_per_trade > 0:
                remaining = strategy_pnl_per_trade - cost_after
                if remaining <= 0:
                    sensitivity = "HIGH"
                elif remaining < strategy_pnl_per_trade * 0.3:
                    sensitivity = "MEDIUM"
                else:
                    sensitivity = "LOW"
            else:
                sensitivity = "HIGH" if increase_pct > 50 else "MEDIUM"

            results.append(StressResult(
                scenario_name=sc["name"],
                spread_multiplier=sc["spread_mult"],
                total_cost_before=cost_before,
                total_cost_after=cost_after,
                cost_increase_pct=increase_pct,
                sensitivity=sensitivity,
            ))

        return results

    @classmethod
    def default_scenarios(cls) -> "CostStressAnalyzer":
        analyzer = cls()
        analyzer.add_scenario("base", 1.0)
        analyzer.add_scenario("stress_1.5x", 1.5)
        analyzer.add_scenario("stress_2.0x", 2.0)
        analyzer.add_scenario("stress_3.0x", 3.0)
        return analyzer

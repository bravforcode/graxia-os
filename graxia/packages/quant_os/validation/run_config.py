from dataclasses import dataclass
from typing import Optional
from .locked_inputs import LockedInputs
from .cost_scenarios import CostScenario, BASE

@dataclass
class RunConfig:
    """Configuration for a single validation run."""
    run_id: str
    run_type: str  # "native", "oracle", "regime", "oos", "concentration"
    locked_inputs: LockedInputs
    cost_scenario: CostScenario = BASE
    symbol: str = "XAUUSD"
    timeframe: str = "H1"
    engine: str = "quant_os"  # "quant_os", "vectorbt", "backtesting_py", "backtrader"
    regime: Optional[str] = None  # None = all regimes
    is_locked_oos: bool = False

    def description(self) -> str:
        parts = [self.run_type, self.engine, self.cost_scenario.label]
        if self.regime:
            parts.append(f"regime={self.regime}")
        if self.is_locked_oos:
            parts.append("LOCKED_OOS")
        return " | ".join(parts)

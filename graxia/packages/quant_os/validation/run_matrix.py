"""Phase BE-P6 — Run matrix for locked revalidation."""
from dataclasses import dataclass


@dataclass
class RunConfig:
    run_id: str
    description: str
    cost_scenario: str
    use_oracle: bool = False
    oracle_name: str = ""
    is_walk_forward: bool = False
    is_final_holdout: bool = False
    is_bootstrap: bool = False
    is_session_exclusion: bool = False


class RunMatrix:
    """BE-P6 run matrix: R0-R10."""

    @staticmethod
    def default() -> list[RunConfig]:
        return [
            RunConfig("R0", "Real data, base observed-spread", "base"),
            RunConfig("R1", "Real data, 1.5x stressed costs", "stress_1"),
            RunConfig("R2", "Real data, 2.0x costs + adverse swap", "stress_2"),
            RunConfig("R3", "Real data, 3.0x costs + severe gap", "stress_3"),
            RunConfig("R4", "Real data, session/event exclusion", "base", is_session_exclusion=True),
            RunConfig("R5", "VectorBT normalized reproduction", "base", use_oracle=True, oracle_name="vectorbt"),
            RunConfig("R6", "Backtesting.py normalized reproduction", "base", use_oracle=True, oracle_name="backtesting_py"),
            RunConfig("R7", "Backtrader normalized reproduction", "base", use_oracle=True, oracle_name="backtrader"),
            RunConfig("R8", "Walk-forward folds", "base", is_walk_forward=True),
            RunConfig("R9", "Final locked holdout only", "base", is_final_holdout=True),
            RunConfig("R10", "Bootstrap / trade-order perturbation", "base", is_bootstrap=True),
        ]

    @staticmethod
    def get_by_id(run_id: str) -> RunConfig | None:
        for r in RunMatrix.default():
            if r.run_id == run_id:
                return r
        return None

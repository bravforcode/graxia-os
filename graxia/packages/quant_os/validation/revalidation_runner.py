"""Phase BE-P6 — Revalidation runner. Executes R0-R10 and evaluates gates."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, asdict


@dataclass
class RunResult:
    run_id: str
    trade_count: int
    time_segments: int
    median_segment_expectancy: float
    expectancy_after_stress_1: float
    profit_factor_after_stress_1: float
    max_single_trade_pnl_pct: float
    max_single_month_pnl_pct: float
    majority_positive_oos: bool
    oracle_match: bool
    ledger_integrity: bool
    data_incidents: int
    verdict: str  # CONTINUE_TO_SHADOW, ARCHIVE_NO_EDGE, INSUFFICIENT_SAMPLE, INVALID_RUN


class RevalidationRunner:
    """Execute revalidation runs and evaluate against gates."""

    def __init__(self, gates_path: str = ""):
        self._gates = self._load_gates(gates_path)
        self._results: list[RunResult] = []

    def _load_gates(self, path: str) -> dict:
        """Load pre-committed gates from YAML."""
        try:
            import yaml
            p = Path(path) if path else Path(__file__).parent / "decision_gates.yaml"
            if p.exists():
                return yaml.safe_load(p.read_text())
        except Exception:
            pass
        # Default gates
        return {
            "xau_candidate_gate": {
                "minimum_effective_oos_trades": 100,
                "minimum_time_segments": 12,
                "positive_median_segment_expectancy": True,
                "positive_expectancy_after_stress_1": True,
                "profit_factor_after_stress_1_min": 1.10,
                "no_single_trade_pnl_share_over_pct": 20,
                "no_single_month_pnl_share_over_pct": 35,
                "majority_positive_oos_folds": True,
                "require_oracle_decision_alignment": True,
                "require_ledger_integrity": True,
                "require_no_unresolved_data_incident": True,
                "require_precommitted_threshold_hash": True,
            }
        }

    def evaluate(self, result: RunResult) -> str:
        """Evaluate a single run against gates. Returns verdict."""
        gates = self._gates.get("xau_candidate_gate", {})

        if result.verdict == "INVALID_RUN":
            return "INVALID_RUN"

        if result.trade_count < gates.get("minimum_effective_oos_trades", 100):
            return "INSUFFICIENT_SAMPLE"

        if result.time_segments < gates.get("minimum_time_segments", 12):
            return "INSUFFICIENT_SAMPLE"

        if not result.ledger_integrity:
            return "INVALID_RUN"

        if result.data_incidents > 0:
            return "INVALID_RUN"

        # Check profitability gates
        if result.median_segment_expectancy <= 0 and gates.get("positive_median_segment_expectancy"):
            return "ARCHIVE_NO_EDGE"

        if result.expectancy_after_stress_1 <= 0 and gates.get("positive_expectancy_after_stress_1"):
            return "ARCHIVE_NO_EDGE"

        if result.profit_factor_after_stress_1 < gates.get("profit_factor_after_stress_1_min", 1.10):
            return "ARCHIVE_NO_EDGE"

        if result.max_single_trade_pnl_pct > gates.get("no_single_trade_pnl_share_over_pct", 20):
            return "ARCHIVE_NO_EDGE"

        if result.max_single_month_pnl_pct > gates.get("no_single_month_pnl_share_over_pct", 35):
            return "ARCHIVE_NO_EDGE"

        if not result.majority_positive_oos and gates.get("majority_positive_oos_folds"):
            return "ARCHIVE_NO_EDGE"

        if not result.oracle_match and gates.get("require_oracle_decision_alignment"):
            return "ARCHIVE_NO_EDGE"

        return "CONTINUE_TO_SHADOW"

    def add_result(self, result: RunResult) -> str:
        """Add result and return evaluated verdict."""
        verdict = self.evaluate(result)
        result.verdict = verdict
        self._results.append(result)
        return verdict

    def final_verdict(self) -> str:
        """Determine final verdict across all runs."""
        if not self._results:
            return "INVALID_RUN"

        verdicts = [r.verdict for r in self._results]

        if "INVALID_RUN" in verdicts:
            return "INVALID_RUN"

        if all(v == "INSUFFICIENT_SAMPLE" for v in verdicts):
            return "INSUFFICIENT_SAMPLE"

        if any(v == "ARCHIVE_NO_EDGE" for v in verdicts):
            return "ARCHIVE_NO_EDGE"

        if all(v == "CONTINUE_TO_SHADOW" for v in verdicts):
            return "CONTINUE_TO_SHADOW"

        return "ARCHIVE_NO_EDGE"

    def get_results(self) -> list[RunResult]:
        return self._results.copy()

    def to_report(self) -> dict:
        return {
            "total_runs": len(self._results),
            "verdicts": [r.verdict for r in self._results],
            "final_verdict": self.final_verdict(),
            "results": [asdict(r) for r in self._results],
        }

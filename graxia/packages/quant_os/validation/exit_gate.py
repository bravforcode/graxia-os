from dataclasses import dataclass, field
from typing import List
import hashlib
import json


@dataclass
class ExitGateCheck:
    name: str
    passed: bool
    evidence: str
    details: str = ""


@dataclass
class ExitGateResult:
    checks: List[ExitGateCheck] = field(default_factory=list)
    verdict: str = "UNKNOWN"  # CONTINUE_RESEARCH, INSUFFICIENT_SAMPLE, ARCHIVE_NO_EDGE, UNKNOWN

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def add_check(self, name: str, passed: bool, evidence: str, details: str = "") -> None:
        self.checks.append(ExitGateCheck(name=name, passed=passed, evidence=evidence, details=details))

    def evaluate_verdict(self) -> str:
        if not self.all_passed:
            failed = [c.name for c in self.checks if not c.passed]
            if any("SAMPLE" in f or "TRADE_COUNT" in f or "MIN_TRADES" in f for f in failed):
                self.verdict = "INSUFFICIENT_SAMPLE"
            else:
                self.verdict = "ARCHIVE_NO_EDGE"
        else:
            self.verdict = "CONTINUE_RESEARCH"
        return self.verdict

    def to_dict(self) -> dict:
        return {
            "checks": [{"name": c.name, "passed": c.passed, "evidence": c.evidence} for c in self.checks],
            "verdict": self.verdict,
            "all_passed": self.all_passed,
        }

    def fingerprint(self) -> str:
        data = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()


class ExitGateEvaluator:
    """Evaluate all Phase 3B exit gate criteria."""

    def __init__(self):
        self._result = ExitGateResult()

    def check_min_trades(self, total_trades: int, min_required: int = 30) -> None:
        passed = total_trades >= min_required
        self._result.add_check(
            "MIN_TRADES",
            passed,
            f"total_trades={total_trades}, required={min_required}",
            "Need enough OOS trades to assess uncertainty"
        )

    def check_positive_stressed_expectancy(self, stress_results: list) -> None:
        """At least one stress scenario must have positive expectancy."""
        positive = any(r.expectancy > 0 for r in stress_results if r.error is None)
        best = max((r.expectancy for r in stress_results if r.error is None), default=0)
        self._result.add_check(
            "POSITIVE_STRESSED_EXPECTANCY",
            positive,
            f"best_stress_expectancy={best:.4f}",
            "Positive stressed-cost expectancy required"
        )

    def check_no_engine_mismatch(self, native_hash: str, oracle_hashes: dict) -> None:
        """All oracle engines should produce matching results within tolerance."""
        mismatches = []
        for engine, h in oracle_hashes.items():
            if h != native_hash:
                mismatches.append(engine)
        passed = len(mismatches) == 0
        self._result.add_check(
            "NO_ENGINE_MISMATCH",
            passed,
            f"mismatched_engines={mismatches}" if mismatches else "all_engines_match",
            "No engine mismatch allowed"
        )

    def check_no_single_trade_dominates(self, concentration) -> None:
        passed, issues = concentration.passes()
        self._result.add_check(
            "NO_SINGLE_TRADE_DOMINATES",
            passed,
            f"max_trade_pct={concentration.max_single_trade_pct_of_total:.1%}, max_month_pct={concentration.max_month_pct_of_total:.1%}",
            "; ".join(issues) if issues else "concentration within limits"
        )

    def check_regime_stability(self, slices: list) -> None:
        """Behavior should be stable across multiple regimes."""
        if not slices:
            self._result.add_check("REGIME_STABILITY", False, "no_regime_slices", "No regime data")
            return
        regimes_with_trades = [s for s in slices if s.trade_count > 0]
        regimes_with_positive_pnl = [s for s in regimes_with_trades if s.total_pnl > 0]
        stability_ratio = len(regimes_with_positive_pnl) / len(regimes_with_trades) if regimes_with_trades else 0
        passed = stability_ratio >= 0.5 and len(regimes_with_trades) >= 2
        self._result.add_check(
            "REGIME_STABILITY",
            passed,
            f"regimes_with_trades={len(regimes_with_trades)}, positive_pnl_ratio={stability_ratio:.1%}",
            "Stable behavior across multiple regimes"
        )

    def check_no_parameter_change(self, locked_inputs_match: bool) -> None:
        self._result.add_check(
            "NO_PARAMETER_CHANGE",
            locked_inputs_match,
            "locked_inputs_verified" if locked_inputs_match else "locked_inputs_mismatch",
            "No parameter change during validation"
        )

    def check_drawdown_within_limits(self, max_drawdown_pct: float, limit_pct: float = 25.0) -> None:
        passed = max_drawdown_pct <= limit_pct
        self._result.add_check(
            "DRAWDOWN_WITHIN_LIMITS",
            passed,
            f"max_drawdown={max_drawdown_pct:.1f}%, limit={limit_pct}%",
            "Drawdown within locked risk framework"
        )

    def check_ledger_integrity(self, ledger_valid: bool) -> None:
        self._result.add_check(
            "LEDGER_INTEGRITY",
            ledger_valid,
            "ledger_hash_chain_valid" if ledger_valid else "ledger_hash_chain_broken",
            "Ledger integrity complete"
        )

    def evaluate(self) -> ExitGateResult:
        self._result.evaluate_verdict()
        return self._result

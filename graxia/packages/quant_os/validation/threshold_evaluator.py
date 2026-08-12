"""Phase BE-P6 — Threshold evaluator for pre-committed gates."""
from dataclasses import dataclass


@dataclass
class ThresholdResult:
    gate_name: str
    expected: str
    actual: str
    passed: bool


class ThresholdEvaluator:
    """Evaluate results against pre-committed thresholds."""
    
    def __init__(self, gates: dict = None):
        self._gates = gates or {}
        self._results: list[ThresholdResult] = []
    
    def evaluate_gate(self, gate_name: str, actual_value, threshold_value,
                      comparator: str = "gte") -> ThresholdResult:
        """Evaluate a single gate."""
        if comparator == "gte":
            passed = actual_value >= threshold_value
        elif comparator == "lte":
            passed = actual_value <= threshold_value
        elif comparator == "eq":
            passed = actual_value == threshold_value
        elif comparator == "neq":
            passed = actual_value != threshold_value
        elif comparator == "bool":
            passed = bool(actual_value) == bool(threshold_value)
        else:
            passed = False
        
        result = ThresholdResult(
            gate_name=gate_name,
            expected=f"{comparator} {threshold_value}",
            actual=str(actual_value),
            passed=passed,
        )
        self._results.append(result)
        return result
    
    def evaluate_all(self, metrics: dict) -> list[ThresholdResult]:
        """Evaluate all gates against metrics."""
        results = []
        
        if "trade_count" in metrics and "min_trades" in self._gates:
            results.append(self.evaluate_gate(
                "min_trades", metrics["trade_count"], self._gates["min_trades"], "gte"
            ))
        
        if "profit_factor" in metrics and "min_profit_factor" in self._gates:
            results.append(self.evaluate_gate(
                "min_profit_factor", metrics["profit_factor"], self._gates["min_profit_factor"], "gte"
            ))
        
        if "max_drawdown_pct" in metrics and "max_drawdown_pct" in self._gates:
            results.append(self.evaluate_gate(
                "max_drawdown_pct", metrics["max_drawdown_pct"], self._gates["max_drawdown_pct"], "lte"
            ))
        
        if "win_rate" in metrics and "min_win_rate" in self._gates:
            results.append(self.evaluate_gate(
                "min_win_rate", metrics["win_rate"], self._gates["min_win_rate"], "gte"
            ))
        
        return results
    
    def all_passed(self) -> bool:
        return all(r.passed for r in self._results)
    
    def get_results(self) -> list[ThresholdResult]:
        return self._results.copy()
    
    def summary(self) -> dict:
        passed = sum(1 for r in self._results if r.passed)
        return {
            "total": len(self._results),
            "passed": passed,
            "failed": len(self._results) - passed,
            "all_passed": self.all_passed(),
        }

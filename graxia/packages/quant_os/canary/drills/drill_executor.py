"""Phase 8 — Drill executor."""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional
from .drill_definitions import DrillType, DrillResult, DRILL_CATALOG


class DrillExecutor:
    """Execute incident drills and record results."""
    
    def __init__(self):
        self._results: list[DrillResult] = []
        self._drill_fn: dict[DrillType, Callable] = {}
    
    def register_drill(self, drill_type: DrillType, fn: Callable) -> None:
        self._drill_fn[drill_type] = fn
    
    def execute(self, drill_type: DrillType) -> DrillResult:
        """Execute a single drill."""
        if drill_type not in self._drill_fn:
            return DrillResult(
                drill_type=drill_type,
                passed=False,
                artifact_path="",
                expected_behavior=DRILL_CATALOG[drill_type].expected_outcome,
                observed_behavior="Drill not registered",
                duration_seconds=0,
            )
        
        start = datetime.now(timezone.utc)
        try:
            self._drill_fn[drill_type]()
            passed = True
            observed = "Drill completed successfully"
        except Exception as e:
            passed = False
            observed = f"Drill failed: {e}"
        
        duration = (datetime.now(timezone.utc) - start).total_seconds()
        
        result = DrillResult(
            drill_type=drill_type,
            passed=passed,
            artifact_path=f"drill_{drill_type.value}_{start.strftime('%Y%m%d_%H%M%S')}.json",
            expected_behavior=DRILL_CATALOG[drill_type].expected_outcome,
            observed_behavior=observed,
            duration_seconds=duration,
        )
        self._results.append(result)
        return result
    
    def execute_all(self) -> list[DrillResult]:
        """Execute all registered drills."""
        for drill_type in DRILL_CATALOG:
            if drill_type in self._drill_fn:
                self.execute(drill_type)
        return list(self._results)
    
    def get_summary(self) -> dict:
        total = len(self._results)
        passed = sum(1 for r in self._results if r.passed)
        return {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "verdict": "PASS" if passed == total else "FAIL",
        }

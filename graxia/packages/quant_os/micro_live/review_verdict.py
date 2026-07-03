"""Phase BE-P12 — Micro-live review verdict."""
from dataclasses import dataclass


@dataclass
class VerdictCheck:
    check_name: str
    passed: bool
    detail: str = ""


class MicroLiveVerdict:
    """Evaluate micro-live for promotion."""

    VERDICTS = ["ARCHIVE", "RETURN_TO_RESEARCH", "EXTEND_MICRO_LIVE", "ELIGIBLE_FOR_EXPANSION"]

    def __init__(self):
        self._checks: list[VerdictCheck] = []

    def evaluate(self, evidence: dict) -> str:
        """Evaluate micro-live evidence. Returns verdict."""
        self._checks = []

        self._checks.append(VerdictCheck(
            "stable_operations",
            evidence.get("critical_incidents", 0) == 0,
            f"critical={evidence.get('critical_incidents', 0)}",
        ))

        self._checks.append(VerdictCheck(
            "reconciled_orders",
            evidence.get("reconciliation_pct", 0) == 100,
            f"reconciliation={evidence.get('reconciliation_pct', 0)}%",
        ))

        self._checks.append(VerdictCheck(
            "cost_gap_stable",
            evidence.get("cost_gap_pct", 100) <= 50,
            f"gap={evidence.get('cost_gap_pct', 100)}%",
        ))

        self._checks.append(VerdictCheck(
            "no_safety_incidents",
            evidence.get("safety_incidents", 0) == 0,
            f"safety={evidence.get('safety_incidents', 0)}",
        ))

        self._checks.append(VerdictCheck(
            "sufficient_window",
            evidence.get("days_run", 0) >= 30,
            f"days={evidence.get('days_run', 0)}",
        ))

        passed = sum(1 for c in self._checks if c.passed)
        total = len(self._checks)

        if passed == total:
            return "ELIGIBLE_FOR_EXPANSION"
        elif evidence.get("critical_incidents", 0) > 0:
            return "ARCHIVE"
        elif evidence.get("days_run", 0) < 30:
            return "EXTEND_MICRO_LIVE"
        else:
            return "RETURN_TO_RESEARCH"

    def get_checks(self) -> list[VerdictCheck]:
        return self._checks.copy()

    def summary(self) -> dict:
        passed = sum(1 for c in self._checks if c.passed)
        return {"total": len(self._checks), "passed": passed, "all_passed": passed == len(self._checks)}

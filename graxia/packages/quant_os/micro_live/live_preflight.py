"""Phase BE-P12 — Live preflight checker."""
from dataclasses import dataclass


@dataclass
class LiveCheck:
    check_name: str
    description: str
    passed: bool = False
    detail: str = ""


class LivePreflight:
    """Check all preconditions before micro-live orders."""

    def __init__(self):
        self._checks: list[LiveCheck] = []

    def check_all(self, context: dict) -> list[LiveCheck]:
        self._checks = []

        self._checks.append(LiveCheck(
            "signed_promotion_decision",
            "Explicit signed promotion decision exists",
            context.get("promotion_decision", False),
        ))

        self._checks.append(LiveCheck(
            "separate_live_profile",
            "Separate live broker profile configured",
            context.get("separate_live_profile", False),
        ))

        self._checks.append(LiveCheck(
            "separate_live_secrets",
            "Separate live secret reference",
            context.get("separate_live_secrets", False),
        ))

        self._checks.append(LiveCheck(
            "independent_risk_ledger",
            "Independent live risk ledger",
            context.get("independent_risk_ledger", False),
        ))

        self._checks.append(LiveCheck(
            "operator_enablement",
            "Operator enablement confirmed",
            context.get("operator_enablement", False),
        ))

        self._checks.append(LiveCheck(
            "broker_healthy",
            "Recent healthy broker verification",
            context.get("broker_healthy", False),
        ))

        self._checks.append(LiveCheck(
            "demo_gates_passed",
            "All demo gates passed",
            context.get("demo_gates_passed", False),
        ))

        return self._checks

    def all_passed(self) -> bool:
        return all(c.passed for c in self._checks)

    def get_failed(self) -> list[LiveCheck]:
        return [c for c in self._checks if not c.passed]

    def summary(self) -> dict:
        passed = sum(1 for c in self._checks if c.passed)
        failed = len(self._checks) - passed
        return {"total": len(self._checks), "passed": passed, "failed": failed, "all_passed": self.all_passed()}

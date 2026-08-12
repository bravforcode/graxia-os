"""Phase BE-P9 — Demo preflight check. Blocks if preconditions not met."""
from dataclasses import dataclass


@dataclass
class PreflightCheck:
    check_name: str
    passed: bool
    detail: str = ""


class DemoPreflight:
    """Check all preconditions before demo order submission."""

    def __init__(self):
        self._checks: list[PreflightCheck] = []

    def check_all(self, context: dict) -> list[PreflightCheck]:
        """Check all preconditions."""
        self._checks = []

        self._checks.append(PreflightCheck(
            "prior_phases_passed",
            context.get("prior_phases_passed", False),
            "BE-P0 through BE-P8 must pass first",
        ))

        self._checks.append(PreflightCheck(
            "operator_enablement",
            context.get("operator_enablement", False),
            "Explicit operator enablement token required",
        ))

        self._checks.append(PreflightCheck(
            "account_mode_demo",
            context.get("account_mode") == "DEMO",
            f"account_mode={context.get('account_mode')}",
        ))

        self._checks.append(PreflightCheck(
            "strategy_eligible",
            context.get("strategy_eligible", False),
            "One strategy must be formally eligible",
        ))

        self._checks.append(PreflightCheck(
            "symbol_eligible",
            context.get("symbol_eligible", False),
            "One symbol must be formally eligible",
        ))

        self._checks.append(PreflightCheck(
            "contract_snapshot_fresh",
            context.get("contract_snapshot_fresh", False),
            "Contract snapshot must be fresh",
        ))

        self._checks.append(PreflightCheck(
            "market_health_green",
            context.get("market_health_green", False),
            "Market health must be HEALTHY",
        ))

        self._checks.append(PreflightCheck(
            "event_risk_clear",
            context.get("event_risk_clear", False),
            "Event-risk state must be CLEAR",
        ))

        self._checks.append(PreflightCheck(
            "kill_switch_armed",
            context.get("kill_switch_armed", False),
            "Kill switch must be armed",
        ))

        return self._checks

    def all_passed(self) -> bool:
        return all(c.passed for c in self._checks)

    def get_failed(self) -> list[PreflightCheck]:
        return [c for c in self._checks if not c.passed]

    def summary(self) -> dict:
        passed = sum(1 for c in self._checks if c.passed)
        return {
            "total": len(self._checks),
            "passed": passed,
            "failed": len(self._checks) - passed,
            "all_passed": self.all_passed(),
        }

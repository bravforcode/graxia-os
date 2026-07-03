"""Phase BE-P10 — Demo scorecard for promotion decisions."""

from dataclasses import dataclass


@dataclass
class ScorecardCheck:
    check_name: str
    description: str
    passed: bool = False
    detail: str = ""


class DemoScorecard:
    """Evaluate demo campaign against promotion gates."""

    def __init__(self):
        self._checks: list[ScorecardCheck] = []

    def evaluate(self, metrics: dict) -> list[ScorecardCheck]:
        """Evaluate all promotion gates."""
        self._checks = []

        self._checks.append(
            ScorecardCheck(
                "no_unexplained_order",
                "All orders have clear signal provenance",
                metrics.get("unexplained_orders", 0) == 0,
                f"unexplained={metrics.get('unexplained_orders', 0)}",
            )
        )

        self._checks.append(
            ScorecardCheck(
                "no_unprotected_position",
                "All positions have protective stops",
                metrics.get("unprotected_positions", 0) == 0,
                f"unprotected={metrics.get('unprotected_positions', 0)}",
            )
        )

        self._checks.append(
            ScorecardCheck(
                "no_stale_data_order",
                "No orders from stale data",
                metrics.get("stale_data_orders", 0) == 0,
                f"stale={metrics.get('stale_data_orders', 0)}",
            )
        )

        self._checks.append(
            ScorecardCheck(
                "no_event_blocked_order",
                "No orders bypassed event gate",
                metrics.get("event_bypass_orders", 0) == 0,
                f"bypass={metrics.get('event_bypass_orders', 0)}",
            )
        )

        self._checks.append(
            ScorecardCheck(
                "no_risk_breach",
                "No risk policy breaches",
                metrics.get("risk_breaches", 0) == 0,
                f"breaches={metrics.get('risk_breaches', 0)}",
            )
        )

        self._checks.append(
            ScorecardCheck(
                "full_reconciliation",
                "100% reconciliation for submitted orders",
                metrics.get("reconciliation_pct", 0) == 100,
                f"reconciliation={metrics.get('reconciliation_pct', 0)}%",
            )
        )

        self._checks.append(
            ScorecardCheck(
                "zero_critical_incidents",
                "Zero unresolved critical incidents",
                metrics.get("critical_incidents", 0) == 0,
                f"critical={metrics.get('critical_incidents', 0)}",
            )
        )

        self._checks.append(
            ScorecardCheck(
                "cost_gap_within_tolerance",
                "Model-to-demo cost gap within tolerance",
                metrics.get("cost_gap_pct", 0) <= 50,
                f"gap={metrics.get('cost_gap_pct', 0)}%",
            )
        )

        self._checks.append(
            ScorecardCheck(
                "labeled_demo_observed",
                "Strategy result labeled DEMO_OBSERVED",
                metrics.get("evidence_label") == "DEMO_OBSERVED",
                f"label={metrics.get('evidence_label')}",
            )
        )

        return self._checks

    def all_passed(self) -> bool:
        return all(c.passed for c in self._checks)

    def get_failed(self) -> list[ScorecardCheck]:
        return [c for c in self._checks if not c.passed]

    def summary(self) -> dict:
        passed = sum(1 for c in self._checks if c.passed)
        return {
            "total": len(self._checks),
            "passed": passed,
            "failed": len(self._checks) - passed,
            "all_passed": self.all_passed(),
        }

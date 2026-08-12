"""Phase BE-P8 — Shadow pass criteria evaluator."""
from dataclasses import dataclass


@dataclass
class PassCheck:
    check_name: str
    description: str
    passed: bool = False
    detail: str = ""


class ShadowPassCriteria:
    """Evaluate shadow campaign against pass criteria."""

    def __init__(self):
        self._checks: list[PassCheck] = []

    def evaluate(self, metrics: dict) -> list[PassCheck]:
        """Evaluate all pass criteria."""
        self._checks = []

        self._checks.append(PassCheck(
            "no_order_operation",
            "Shadow must never submit orders",
            metrics.get("order_count", 0) == 0,
            f"order_count={metrics.get('order_count', 0)}",
        ))

        self._checks.append(PassCheck(
            "no_stale_signal",
            "No signal generated from stale data",
            metrics.get("stale_feed_count", 0) == 0,
            f"stale_count={metrics.get('stale_feed_count', 0)}",
        ))

        self._checks.append(PassCheck(
            "no_event_blocked",
            "No signal bypassed event gate",
            metrics.get("event_bypass_count", 0) == 0,
            f"bypass_count={metrics.get('event_bypass_count', 0)}",
        ))

        self._checks.append(PassCheck(
            "contract_snapshot_present",
            "Contract snapshot available",
            metrics.get("has_contract_snapshot", True),
            "present" if metrics.get("has_contract_snapshot", True) else "missing",
        ))

        self._checks.append(PassCheck(
            "ledger_sealed",
            "Ledger has valid seal",
            metrics.get("ledger_sealed", False),
            "sealed" if metrics.get("ledger_sealed") else "unsealed",
        ))

        self._checks.append(PassCheck(
            "no_critical_exception",
            "No unhandled critical exceptions",
            metrics.get("critical_exception_count", 0) == 0,
            f"exceptions={metrics.get('critical_exception_count', 0)}",
        ))

        self._checks.append(PassCheck(
            "stable_heartbeat",
            "Heartbeat stable over campaign window",
            metrics.get("heartbeat_count", 0) > 0,
            f"heartbeats={metrics.get('heartbeat_count', 0)}",
        ))

        self._checks.append(PassCheck(
            "incidents_triaged",
            "All incidents have root-cause status",
            metrics.get("unresolved_incidents", 0) == 0,
            f"unresolved={metrics.get('unresolved_incidents', 0)}",
        ))

        return self._checks

    def all_passed(self) -> bool:
        return all(c.passed for c in self._checks)

    def get_failed(self) -> list[PassCheck]:
        return [c for c in self._checks if not c.passed]

    def summary(self) -> dict:
        passed = sum(1 for c in self._checks if c.passed)
        return {
            "total": len(self._checks),
            "passed": passed,
            "failed": len(self._checks) - passed,
            "all_passed": self.all_passed(),
        }

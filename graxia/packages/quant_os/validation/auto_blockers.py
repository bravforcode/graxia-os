"""Phase BE-P11 — Automatic blocker checker."""
from dataclasses import dataclass


@dataclass
class BlockerCheck:
    blocker_name: str
    triggered: bool
    detail: str = ""
    severity: str = "blocker"  # blocker, warning


class AutoBlockerChecker:
    """Check all automatic promotion blockers."""

    BLOCKERS = [
        ("unresolved_critical_incidents", "Critical incidents must be resolved"),
        ("unprotected_positions", "All positions must have protective stops"),
        ("reconciliation_mismatch", "100% reconciliation required"),
        ("cost_model_gap", "Cost gap must be within tolerance"),
        ("needs_retuning", "Strategy must not need retuning after demo"),
        ("broker_identity_not_locked", "Broker identity must be locked"),
        ("insufficient_sample", "Trade count must be >= 100"),
        ("oracle_divergence_unresolved", "Oracle divergence must be resolved"),
    ]

    def __init__(self):
        self._results: list[BlockerCheck] = []

    def check(self, context: dict) -> list[BlockerCheck]:
        """Check all blockers against context."""
        self._results = []

        self._results.append(BlockerCheck(
            "unresolved_critical_incidents",
            context.get("critical_incidents", 0) > 0,
            f"critical={context.get('critical_incidents', 0)}",
        ))

        self._results.append(BlockerCheck(
            "unprotected_positions",
            context.get("unprotected_positions", 0) > 0,
            f"unprotected={context.get('unprotected_positions', 0)}",
        ))

        self._results.append(BlockerCheck(
            "reconciliation_mismatch",
            context.get("reconciliation_pct", 100) < 100,
            f"reconciliation={context.get('reconciliation_pct', 100)}%",
        ))

        self._results.append(BlockerCheck(
            "cost_model_gap",
            context.get("cost_gap_pct", 0) > 50,
            f"gap={context.get('cost_gap_pct', 0)}%",
        ))

        self._results.append(BlockerCheck(
            "needs_retuning",
            context.get("needs_retuning", False),
        ))

        self._results.append(BlockerCheck(
            "broker_identity_not_locked",
            not context.get("broker_identity_locked", False),
        ))

        self._results.append(BlockerCheck(
            "insufficient_sample",
            context.get("trade_count", 0) < 100,
            f"trades={context.get('trade_count', 0)}",
        ))

        self._results.append(BlockerCheck(
            "oracle_divergence_unresolved",
            context.get("oracle_divergence", False),
        ))

        return self._results

    def has_blockers(self) -> bool:
        return any(b.triggered for b in self._results)

    def get_triggered(self) -> list[BlockerCheck]:
        return [b for b in self._results if b.triggered]

    def summary(self) -> dict:
        triggered = sum(1 for b in self._results if b.triggered)
        return {
            "total": len(self._results),
            "triggered": triggered,
            "clear": triggered == 0,
        }

"""Phase BE-P4 — Guard against forbidden cost modeling shortcuts."""


FORBIDDEN_SHORTCUTS = [
    "random_normal_slippage",
    "random_latency_distribution",
    "queue_position_without_depth",
    "current_contract_as_historical",
    "demo_fills_as_live_proof",
]


class ForbiddenShortcutsGuard:
    """Rejects forbidden cost modeling approaches."""

    def __init__(self):
        self._violations: list[str] = []

    def check(self, approach: str) -> tuple[bool, str]:
        """Check if approach is forbidden."""
        if approach in FORBIDDEN_SHORTCUTS:
            msg = f"forbidden: {approach} — use labeled evidence instead"
            self._violations.append(msg)
            return False, msg
        return True, "OK"

    def check_all(self, approaches: list[str]) -> tuple[bool, list[str]]:
        """Check multiple approaches."""
        issues = []
        for approach in approaches:
            ok, msg = self.check(approach)
            if not ok:
                issues.append(msg)
        return len(issues) == 0, issues

    def get_violations(self) -> list[str]:
        return self._violations.copy()

    def is_clean(self) -> bool:
        return len(self._violations) == 0

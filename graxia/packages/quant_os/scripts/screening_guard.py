"""Post-run guard enforcement for Direction I screening (spec §5 P4, A11).

Supplement to Tier0 Sweep Stream C0 (reused, not re-implemented): the
screening runner MUST assert zero guard violations after every
BacktestEngine.run() — a violation voids the run (still counts N) and
triggers audit. attr_scan() snapshots strategy attributes before a run
and reports mutations after (scan_for_data_leaks()-equivalent channel).
"""

from __future__ import annotations


class GuardViolationError(RuntimeError):
    pass


def assert_no_guard_violations(engine, *, config_id: str) -> None:
    violations = list(getattr(getattr(engine, "guard", None), "violations", None) or [])
    if violations:
        raise GuardViolationError(
            f"config_id={config_id}: {len(violations)} guard violation(s) — run VOID, audit required"
        )


def attr_scan(strategy, before: dict) -> list[str]:
    after = dict(vars(strategy))
    return sorted(k for k in before if before.get(k) != after.get(k))

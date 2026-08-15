"""Post-run guard enforcement for Direction I screening (spec §5 P4, A11).

Supplement to Tier0 Sweep Stream C0 (reused, not re-implemented): the
screening runner MUST assert zero guard violations after every
BacktestEngine.run() — a violation voids the run (still counts N) and
triggers audit. Fail-closed: an engine WITHOUT a `.guard` attribute is a
wiring error and raises (review #3) — a silent no-op would defeat the
whole enforcement. attr_scan() snapshots strategy attributes before a run
and reports ANY difference after (including attributes ADDED mid-run —
review #4, the suspicious leak pattern).
"""

from __future__ import annotations


class GuardViolationError(RuntimeError):
    pass


def assert_no_guard_violations(engine, *, config_id: str) -> None:
    guard = getattr(engine, "guard", None)
    if guard is None:
        raise GuardViolationError(
            f"config_id={config_id}: engine has no .guard attribute — fail-closed, run VOID "
            "(wiring: P4 runner / Tier0 C0 must attach engine.guard)"
        )
    violations = list(getattr(guard, "violations", None) or [])
    if violations:
        raise GuardViolationError(
            f"config_id={config_id}: {len(violations)} guard violation(s) — run VOID, audit required"
        )


def attr_scan(strategy, before: dict) -> list[str]:
    after = dict(vars(strategy))
    keys = set(before) | set(after)
    return sorted(k for k in keys if before.get(k) != after.get(k))

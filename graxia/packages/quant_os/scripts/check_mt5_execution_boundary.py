#!/usr/bin/env python3
"""
CI check: no new script may call MT5 order_send/order_modify directly without
either (a) living in the approved execution layer, or (b) carrying the
QUANT_OS_ALLOW_UNVALIDATED_LIVE guard clause.

Root cause this closes: reports/incident_unvalidated_scripts_20260717.md —
"any Python script can call mt5.order_send() directly, bypassing the
orchestrator/OMS/KillSwitch/PreTradeRiskGate." This does not retroactively
fix every legacy script (many are grandfathered via the guard clause added
2026-07-20); it prevents a NEW ungated script from being added silently.

Usage: python scripts/check_mt5_execution_boundary.py
Exit 0 = clean, exit 1 = violation(s) found (prints file:line).
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ORDER_CALL_RE = re.compile(r"\.order_send\(|\.order_modify\(")
GUARD_MARKER = "QUANT_OS_ALLOW_UNVALIDATED_LIVE"

# Approved execution layer: routes orders through OMS/KillSwitch/PreTradeRiskGate,
# or is a documented safety-critical exception (dead man's switch must be able to
# flatten positions even if the OMS path is degraded).
ALLOWLIST = {
    "execution/adapters/mt5.py",
    "execution/broker_adapter.py",
    "monitoring/dead_mans_switch.py",
}

# Directories excluded from the scan entirely: test suites (mock MT5, don't
# place real orders) and the .freebuff worktree (a separate git worktree, not
# part of this working tree).
EXCLUDED_DIR_PARTS = {".freebuff", "tests", ".git", "__pycache__", "node_modules"}


def is_excluded(path: Path) -> bool:
    parts = set(path.relative_to(ROOT).parts[:-1])
    if parts & EXCLUDED_DIR_PARTS:
        return True
    name = path.name
    # Test-like files living outside tests/ (e.g. shadow/test_*.py) also excluded.
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    return False


def main() -> int:
    violations = []
    for path in ROOT.rglob("*.py"):
        if is_excluded(path):
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel in ALLOWLIST:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not ORDER_CALL_RE.search(text):
            continue
        if GUARD_MARKER in text:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if ORDER_CALL_RE.search(line):
                violations.append(f"{rel}:{i}: {line.strip()}")

    if violations:
        print("MT5 execution boundary violation(s) found:")
        print()
        for v in violations:
            print(f"  {v}")
        print()
        print(
            "Files calling MT5 order_send/order_modify directly must either:\n"
            "  1. Live in the approved execution layer "
            f"({', '.join(sorted(ALLOWLIST))}), or\n"
            "  2. Carry the QUANT_OS_ALLOW_UNVALIDATED_LIVE guard clause "
            "(see scripts/live_donchian.py for the pattern).\n"
            "See reports/incident_unvalidated_scripts_20260717.md for why this matters."
        )
        return 1

    print("MT5 execution boundary check: clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

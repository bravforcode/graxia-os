"""Trial 4002 re-review gate — run at 30/90/180-day marks.

Evaluates whether the funding-arb paper phase should continue or stop,
per the pre-registration re-review triggers (30/90/180 days since 2026-07-28,
or cumulative net funding < -1x entry_cost per leg).

Exit codes: 0 = continue, 1 = stop recommended (trigger hit).
Prints the current state + recommendation. Intended to be run by the
scheduled task 'quant_os_funding_arb_review' (one-shot per milestone).
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "reports" / "paper_trading" / "funding_arb_state.json"
MILESTONES = {30: "2026-08-27", 90: "2026-10-26", 180: "2027-01-24"}
OPENED = datetime(2026, 7, 28, tzinfo=UTC)


def main() -> int:
    if not STATE_PATH.exists():
        print("FAIL: state file missing")
        return 1
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    now = datetime.now(UTC)
    days_open = (now - OPENED).days

    print(f"Trial 4002 re-review — day {days_open} (milestones: {MILESTONES})")
    stop_flags = []
    for sym, pos in state.get("positions", {}).items():
        net = pos.get("cumulative_funding_usd", 0.0) - pos.get("entry_cost_usd", 0.0)
        cost = pos.get("entry_cost_usd", 0.0)
        print(f"  {sym}: net=${net:+.4f} (entry_cost=${cost:.2f})")
        if cost > 0 and net < -cost:
            stop_flags.append(f"{sym} net < -1x entry_cost")

    milestone_hit = any(now.date().isoformat() >= d for d in MILESTONES.values())
    if milestone_hit:
        print(f"\nMILESTONE REACHED: {days_open} days since 2026-07-28 — re-review required.")
    if stop_flags:
        print(f"STOP TRIGGER: {'; '.join(stop_flags)}")
        print("RECOMMENDATION: stop paper phase / re-evaluate hypothesis.")
        return 1
    if milestone_hit:
        print("RECOMMENDATION: milestone reached — human review of paper PnL vs T-bill baseline required.")
        return 0
    print("RECOMMENDATION: continue accumulating (no trigger hit).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

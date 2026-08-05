"""Health gate for the Trial #4002 funding-arb paper-trade collector.

Reads reports/paper_trading/funding_arb_state.json and exits non-zero if:
  1. state file missing, or no open paper positions, or
  2. last_checked_at is older than --max-stale-hours (default 12) -- i.e. a
     Binance funding interval (8h) has gone unrecorded.

Exit codes: 0 = healthy, 1 = stale/missing (guard failure). Usable as a CLI
gate now; can be wired into Telegram/Prometheus alerting later.

Usage:
    python scripts/check_funding_arb_health.py [--max-stale-hours 12]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "reports" / "paper_trading" / "funding_arb_state.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--max-stale-hours",
        type=float,
        default=12.0,
        help="Max allowed age of last_checked_at before the gate fails (default 12)",
    )
    args = parser.parse_args()

    if not STATE_PATH.exists():
        print(f"FAIL: state file missing: {STATE_PATH}")
        return 1

    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    positions = state.get("positions") or {}
    if not positions:
        print("FAIL: no open paper positions in state")
        return 1

    now = datetime.now(UTC)
    stale = False
    for symbol, pos in positions.items():
        last = pos.get("last_checked_at")
        if not last:
            print(f"FAIL: {symbol} missing last_checked_at")
            stale = True
            continue
        age_h = (now - datetime.fromisoformat(last)).total_seconds() / 3600
        net = pos.get("cumulative_funding_usd", 0.0) - pos.get("entry_cost_usd", 0.0)
        print(f"  {symbol:<10} last_checked {age_h:5.1f}h ago  net=${net:+.4f}")
        if age_h > args.max_stale_hours:
            stale = True

    if stale:
        print(f"FAIL: collector stale (>{args.max_stale_hours:.0f}h) -- "
              "funding events may have been missed")
        return 1

    print("OK: collector healthy")
    return 0


if __name__ == "__main__":
    sys.exit(main())

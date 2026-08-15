"""Auto-increment trial counter — maintains cumulative trial ledger.

Reads research/trial_ledger.json, validates cap not reached,
allocates next trial number, writes updated ledger.

Usage:
    python research/auto_increment_trial.py
    python research/auto_increment_trial.py --hypothesis HYP_ID --name "Name" --arm A
    python research/auto_increment_trial.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

LEDGER_PATH = Path(__file__).parent / "trial_ledger.json"
REGISTRY_PATH = Path(__file__).parent / "hypothesis_registry.json"


def load_json(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"ERROR: {path} not found.")
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def allocate(ledger: dict) -> int:
    nxt = ledger["next_available_trial_number"]
    cap = ledger["cumulative_trial_cap"]
    if nxt > cap:
        sys.exit(
            f"STOPPING RULE TRIGGERED: cap {cap} reached. "
            f"Per stopping_rule_2026_07_30.md §3.1 (supersedes stopping_rule_2026_07_12.md), "
            f"no further hypotheses. "
            f"Options: A) stop, B) new direction, C) wait for new data."
        )
    return nxt


def main() -> None:
    p = argparse.ArgumentParser(description="Allocate next trial number.")
    p.add_argument("--hypothesis", help="Short snake_case hypothesis id")
    p.add_argument("--name", help="Human-readable hypothesis name")
    p.add_argument("--arm", choices=["A", "B"], help="Arm chosen")
    p.add_argument("--dry-run", action="store_true", help="Print next number without writing")
    args = p.parse_args()

    ledger = load_json(LEDGER_PATH)
    trial = allocate(ledger)

    if args.dry_run:
        print(f"Next available trial number: {trial}")
        return

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    ledger["cumulative_trial_count"] = trial
    ledger["next_available_trial_number"] = trial + 1
    ledger["new_hypotheses_used"] += 1
    ledger["new_hypotheses_remaining"] = max(0, ledger["max_new_hypotheses"] - ledger["new_hypotheses_used"])
    ledger["stopping_rule_triggers"]["trial_cap_1022_reached"]["active"] = (
        ledger["cumulative_trial_count"] >= ledger["cumulative_trial_cap"]
    )
    save_json(LEDGER_PATH, ledger)

    if args.hypothesis and args.name and args.arm:
        registry = load_json(REGISTRY_PATH)
        registry["hypotheses"].append({
            "id": args.hypothesis,
            "name": args.name,
            "arm_chosen": args.arm,
            "status": "PRE_REGISTERED",
            "trial_number": trial,
            "date_pre_registered": today,
            "date": None,
            "result": None,
        })
        registry["next_trial_number"] = trial + 1
        registry["last_updated"] = today
        save_json(REGISTRY_PATH, registry)
        print(f"Allocated trial #{trial} -> {args.hypothesis} (Arm {args.arm}) | {today}")
    else:
        print(f"Allocated trial #{trial} | {today}")


if __name__ == "__main__":
    main()

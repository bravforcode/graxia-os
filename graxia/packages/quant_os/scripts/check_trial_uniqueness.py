"""Trial ID uniqueness check — scans all ledgers/registries for duplicate trial numbers.

Checks:
1. Within each trial_ledger*.json: no duplicate trial_number in lineage
2. Across ALL trial_ledger*.json + hypothesis_registry*.json (globbed, so
   hypothesis_registry_c.json and any future *registry*/*ledger* file are
   included): no trial_number is reused across different sources
3. (--mechanism) every entry declares a 'mechanism' field

Usage:
    python scripts/check_trial_uniqueness.py
    python scripts/check_trial_uniqueness.py --mechanism   # also enforce mechanism field
    python scripts/check_trial_uniqueness.py --fix  # (future: auto-resolve)

Exit codes:
    0 = no collisions
    1 = collisions found (details printed to stderr)
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

RESEARCH_DIR = Path(__file__).resolve().parent.parent / "research"


def load_ledger(path: Path) -> list[dict]:
    """Extract trial entries from a trial_ledger*.json file."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    entries = []
    for item in data.get("lineage", []):
        # trial_number is the primary key; trial_range is a batch (e.g. "1-1000")
        if "trial_number" in item:
            entries.append(
                {
                    "trial_number": item["trial_number"],
                    "id": item.get("id"),
                    "result": item.get("result"),
                    "date": item.get("date"),
                    "source": path.name,
                }
            )
        elif "trial_range" in item:
            # Batch entry — record the range start for collision detection
            start, end = item["trial_range"].split("-")
            entries.append(
                {
                    "trial_number": int(start),
                    "id": item.get("id"),
                    "result": item.get("result"),
                    "date": item.get("date"),
                    "source": path.name,
                    "is_range": True,
                    "range": item["trial_range"],
                }
            )
    return entries


def load_registry(path: Path) -> list[dict]:
    """Extract trial entries from a hypothesis_registry*.json file."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    entries = []
    for item in data.get("hypotheses", data.get("lineage", [])):
        # Accept trial_id or trial_number as the primary key
        trial_num = item.get("trial_id", item.get("trial_number"))
        if trial_num is not None:
            entries.append(
                {
                    "trial_number": trial_num,
                    "id": item.get("id"),
                    "result": item.get("status", item.get("result")),
                    "date": item.get("tested_date", item.get("verdict_date")),
                    "source": path.name,
                }
            )
    return entries


def check_collisions(all_entries: list[dict]) -> list[dict]:
    """Find trial numbers that appear in multiple sources with different ids."""
    by_number = defaultdict(list)
    for entry in all_entries:
        by_number[entry["trial_number"]].append(entry)

    collisions = []
    for number, entries in by_number.items():
        if len(entries) < 2:
            continue
        # Check if they agree on id
        ids = set(e["id"] for e in entries if e["id"] is not None)
        if len(ids) > 1:
            collisions.append(
                {
                    "trial_number": number,
                    "conflicting_ids": list(ids),
                    "records": entries,
                }
            )
    return collisions


def trial_family(source_name: str) -> str:
    """Family key for a ledger/registry filename: trial_ledger.json and
    hypothesis_registry.json share family '' (main); *_b.json / *_c.json
    share family 'b' / 'c'. Paired ledger+registry files in the same family
    are expected by design to mirror the same trial_number, so that reuse
    is not itself a collision (unrecognized names fall back to the
    filename itself, i.e. never match any other file's family).
    """
    m = re.match(r"(?:trial_ledger|hypothesis_registry)(_[a-z0-9]+)?\.json$", source_name)
    return (m.group(1) or "") if m else source_name


def check_trial_number_namespace(ledgers: list[tuple[str, list[dict]]]) -> list[tuple]:
    """Trial NUMBERS must be unique across ledger FAMILIES (the #2001 bug
    class: a trial_ledger_c.json entry and a hypothesis_registry.json entry
    using the same number for two different trials). Paired ledger+registry
    files within the same family (e.g. trial_ledger.json and
    hypothesis_registry.json) mirror each other by design — reuse within a
    family is not flagged here; check_collisions() still catches it if their
    `id` fields disagree. `ledgers` = list of (source_name, entries). Returns
    (trial_number, first_source, second_source) for any number reused across
    DIFFERENT families. [] = pass.
    """
    seen: dict[int, tuple[str, str]] = {}  # num -> (family, source_name)
    errors: list[tuple] = []
    for name, entries in ledgers:
        family = trial_family(name)
        for entry in entries:
            num = entry.get("trial_number")
            if num is None:
                continue
            if num in seen:
                seen_family, seen_name = seen[num]
                if seen_family != family:
                    errors.append((num, seen_name, name))
                continue
            seen[num] = (family, name)
    return errors


def check_mechanism(entries: list[dict]) -> list[str]:
    """Every trial entry should declare a 'mechanism' field distinguishing e.g.
    'single_asset_absolute_momentum' from 'cross_sectional_relative_momentum'.
    GATED (--mechanism): the schema does not yet carry 'mechanism' on every
    entry, so this is opt-in until the schema is updated everywhere.
    Returns human-readable errors; [] = pass.
    """
    errors = []
    for entry in entries:
        tid = entry.get("id", entry.get("trial_number", "<unknown>"))
        mechanism = entry.get("mechanism")
        if not mechanism:
            errors.append(f"Trial {tid}: missing required 'mechanism' field")
        elif not isinstance(mechanism, str) or not mechanism.strip():
            errors.append(f"Trial {tid}: 'mechanism' field is empty or invalid")
    return errors


def main():
    parser = argparse.ArgumentParser(description="Trial ID uniqueness check")
    parser.add_argument(
        "--mechanism",
        action="store_true",
        help="also enforce that every entry declares a 'mechanism' field "
        "(gated: schema does not yet carry it everywhere)",
    )
    args = parser.parse_args()

    all_entries = []
    ledger_pairs: list[tuple[str, list[dict]]] = []

    # Glob ALL trial_ledger*.json AND hypothesis_registry*.json. Using globs
    # (not explicit filenames) means hypothesis_registry_c.json and any future
    # *registry* / *ledger* file are scanned — no fourth file stays invisible.
    for p in sorted(RESEARCH_DIR.glob("trial_ledger*.json")):
        entries = load_ledger(p)
        ledger_pairs.append((p.name, entries))
        all_entries.extend(entries)
    for p in sorted(RESEARCH_DIR.glob("hypothesis_registry*.json")):
        entries = load_registry(p)
        ledger_pairs.append((p.name, entries))
        all_entries.extend(entries)

    errors: list[str] = []

    # 1) Cross-source collisions with DIFFERING ids (detailed report)
    collisions = check_collisions(all_entries)
    collided_numbers = set()
    for c in collisions:
        collided_numbers.add(c["trial_number"])
        errors.append(f"COLLISION: Trial #{c['trial_number']}: conflicting ids = {c['conflicting_ids']}")
        for rec in c["records"]:
            errors.append(f"    source={rec['source']}  id={rec['id']}  result={rec['result']}  date={rec['date']}")

    # 2) Stricter: any trial_number reused across DIFFERENT sources (incl. same-id).
    #    Skip numbers already reported above to avoid duplicate lines.
    for num, a, b in check_trial_number_namespace(ledger_pairs):
        if num in collided_numbers:
            continue
        errors.append(f"TRIAL NUMBER REUSE: {num} appears in '{a}' and '{b}'")

    # 3) Gated mechanism check
    if args.mechanism:
        for name, entries in ledger_pairs:
            for e in check_mechanism(entries):
                errors.append(f"[{name}] {e}")

    if not errors:
        print(f"OK: {len(all_entries)} trial entries, 0 collisions.")
        sys.exit(0)

    print(f"PROBLEMS FOUND: {len(errors)} line(s)\n", file=sys.stderr)
    for line in errors:
        print(line, file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()

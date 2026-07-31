"""Trial ID uniqueness check — scans all ledgers/registries for duplicate trial numbers.

Checks:
1. Within each trial_ledger*.json: no duplicate trial_number in lineage
2. Across ALL trial_ledger*.json + hypothesis_registry*.json (globbed, so
   hypothesis_registry_c.json and any future *registry*/*ledger* file are
   included): no trial_number is reused across different sources
3. (--mechanism) every entry declares a 'mechanism' field

Ratchet (same pattern as check_bypass_loaders.py's BASELINE): trial numbers
3001-3004 are a known, documented cross-direction collision between
Direction B (trial_ledger_b.json / hypothesis_registry_b.json) and Direction
C (trial_ledger_c.json / hypothesis_registry_c.json), recorded as debt in
TRIAL_ID_RANGES.md pending a real renumbering decision (blocked on Direction
C's own registry/ledger disagreeing with each other about trial #3001 vs
#3004 for "BTC vol divergence" -- see TRIAL_ID_RANGES.md). Collisions in
BASELINE are reported but do not fail the check; any collision NOT in
BASELINE does.

Usage:
    python scripts/check_trial_uniqueness.py
    python scripts/check_trial_uniqueness.py --list        # print baseline collisions, exit 0
    python scripts/check_trial_uniqueness.py --mechanism   # also enforce mechanism field
    python scripts/check_trial_uniqueness.py --fix  # (future: auto-resolve)

Exit codes:
    0 = no collisions, or only known BASELINE collisions
    1 = new collisions found outside BASELINE (details printed to stderr)
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

RESEARCH_DIR = Path(__file__).resolve().parent.parent / "research"

# Known, documented trial-number collisions treated as debt, not as new
# failures. Do not add to this set to silence a check -- add a genuinely
# new legitimate exception here only with a reason, same discipline as
# check_bypass_loaders.py's BASELINE.
BASELINE: dict[int, str] = {
    3001: "Direction B (PATHB-CARRY-XAUUSD) vs Direction C (BTCVD-BTC-VOL-DIVERGENCE) -- see TRIAL_ID_RANGES.md",
    3002: "Direction B (PATHB-VRP-XAUUSD) vs Direction C (ETHVC-ETH-VOL-CONFIRM) -- see TRIAL_ID_RANGES.md",
    3003: "Direction B (PATHB-CAM-XAUUSD) vs Direction C (BEVS-BTC-ETH-VOL-SPREAD) -- see TRIAL_ID_RANGES.md",
    3004: "Direction B (PATHB-DXY-DIV-XAUUSD) vs Direction C (btc_vol_divergence) -- see TRIAL_ID_RANGES.md",
}


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
                    "mechanism": item.get("mechanism"),
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
    GATED (--mechanism): trial_ledger*.json's schema does not carry a
    'mechanism' field at all (it's registry-only, e.g. hypothesis_registry.json),
    so every ledger-sourced entry will always fail this check -- that is a real,
    accurate gap, not a bug. hypothesis_registry_b.json and _e.json currently
    have zero 'mechanism' entries either; the others (main, _c, _f) do. This is
    opt-in until the ledger schema is extended to carry 'mechanism' too.
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
    parser.add_argument(
        "--list",
        action="store_true",
        help="print current BASELINE collisions (documented debt) and exit 0",
    )
    parser.add_argument(
        "--census",
        action="store_true",
        help="print every (trial_number, id, source) row across all ledgers/registries, "
        "sorted by number then source, and exit 0. This is the single source of truth "
        "for 'what number maps to what trial where' -- generated from the same glob "
        "load_ledger()/load_registry() use for the checks, so it can't drift out of "
        "sync with reality the way a hand-maintained doc can.",
    )
    args = parser.parse_args()

    if args.list:
        for num, reason in sorted(BASELINE.items()):
            print(f"[baseline] #{num}: {reason}")
        return

    if args.census:
        census_entries = []
        for p in sorted(RESEARCH_DIR.glob("trial_ledger*.json")):
            census_entries.extend(load_ledger(p))
        for p in sorted(RESEARCH_DIR.glob("hypothesis_registry*.json")):
            census_entries.extend(load_registry(p))
        census_entries.sort(key=lambda e: (e["trial_number"], e["source"]))
        print(f"{'number':>7}  {'source':<28}  {'id':<32}  result")
        print(f"{'-' * 7}  {'-' * 28}  {'-' * 32}  {'-' * 10}")
        for e in census_entries:
            print(f"{e['trial_number']:>7}  {e['source']:<28}  {str(e['id']):<32}  {e['result']}")
        print(f"\n{len(census_entries)} total rows across {len({e['source'] for e in census_entries})} files.")
        return

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
    baseline_notes: list[str] = []

    # 1) Cross-source collisions with DIFFERING ids (detailed report).
    #    Numbers in BASELINE are documented debt -- reported but non-fatal;
    #    anything else is a new, unreviewed collision and fails the check.
    collisions = check_collisions(all_entries)
    collided_numbers = set()
    for c in collisions:
        num = c["trial_number"]
        collided_numbers.add(num)
        target = baseline_notes if num in BASELINE else errors
        label = "KNOWN (baseline)" if num in BASELINE else "COLLISION"
        target.append(f"{label}: Trial #{num}: conflicting ids = {c['conflicting_ids']}")
        for rec in c["records"]:
            target.append(f"    source={rec['source']}  id={rec['id']}  result={rec['result']}  date={rec['date']}")
        if num in BASELINE:
            target.append(f"    baseline reason: {BASELINE[num]}")

    # 2) Stricter: any trial_number reused across DIFFERENT sources (incl. same-id).
    #    Skip numbers already reported above to avoid duplicate lines. Never
    #    baseline-exempt: same-id reuse across families is a different, more
    #    serious bug class than the differing-id BASELINE collisions above.
    for num, a, b in check_trial_number_namespace(ledger_pairs):
        if num in collided_numbers:
            continue
        errors.append(f"TRIAL NUMBER REUSE: {num} appears in '{a}' and '{b}'")

    # 3) Gated mechanism check
    if args.mechanism:
        for name, entries in ledger_pairs:
            for msg in check_mechanism(entries):
                errors.append(f"[{name}] {msg}")

    if baseline_notes:
        print(f"BASELINE (documented, non-fatal): {len(baseline_notes)} line(s)")
        for line in baseline_notes:
            print(line)
        print()

    if not errors:
        print(
            f"OK: {len(all_entries)} trial entries, 0 new collisions "
            f"({len(collided_numbers & BASELINE.keys())} baseline exceptions still present)."
        )
        sys.exit(0)

    print(f"PROBLEMS FOUND: {len(errors)} line(s)\n", file=sys.stderr)
    for line in errors:
        print(line, file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()

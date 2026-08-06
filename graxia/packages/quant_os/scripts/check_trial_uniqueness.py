"""Trial ID uniqueness check — scans all ledgers/registries for duplicate trial numbers.

Checks:
1. Within each trial_ledger*.json: no duplicate trial_number in lineage
2. Across ALL trial_ledger*.json + hypothesis_registry*.json (globbed, so
   hypothesis_registry_c.json and any future *registry*/*ledger* file are
   included): no trial_number is reused across different sources
3. Every pre_registration*/trial_NNNN_*.md doc's filename-encoded trial
   number actually exists in a ledger/registry entry within the same family
   (catches the #3001-vs-#3004 class of bug: a doc's filename disagreeing
   with the number its own ledger/registry entry actually uses)
4. (--mechanism) every entry declares a 'mechanism' field

Ratchet (same pattern as check_bypass_loaders.py's BASELINE): historically
trial numbers 3001-3004 were a documented cross-direction collision between
Direction B and Direction C. That collision was resolved 2026-07-31 by
renumbering Direction C to the 7000 block (see TRIAL_ID_RANGES.md) -- B is
now the sole owner of 3001-3008. BASELINE is empty; any collision found is a
real, new problem, not documented debt.

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
BASELINE: dict[int, str] = {}

# Per-direction trial-number ownership (source of truth: TRIAL_ID_RANGES.md).
# family key (from trial_family(), which returns '_b'/'_c'/'_d'/... for
# suffixed files and '' for main) -> (low, high) inclusive owned range.
FAMILY_RANGES: dict[str, tuple[int, int]] = {
    "": (1000, 1999),  # main
    "_b": (3001, 3008),  # Direction B actual (documented 2000-2999, actual 3001-3008)
    "_c": (7000, 7999),
    "_d": (4000, 4999),
    "_e": (5000, 5999),
    "_f": (6000, 6999),
    "_g": (8000, 8999),
    "_h": (9000, 9999),
    "_i": (10000, 10999),
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
                    "mechanism": item.get("mechanism"),
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
                    "mechanism": item.get("mechanism"),
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


def check_family_range_ownership(ledger_pairs: list[tuple[str, list[dict]]]) -> list[str]:
    """Flag trial numbers that fall OUTSIDE their file family's owned range.

    Source of truth: TRIAL_ID_RANGES.md. This is the per-direction hardener for
    the #4002-collision bug class: a session writing trial 4002 into the MAIN
    ledger (family '') instead of Direction D's registry_d (family 'd').
    Returns human-readable errors; [] = pass.
    """
    errors = []
    for name, entries in ledger_pairs:
        family = trial_family(name)
        rng = FAMILY_RANGES.get(family)
        if rng is None:
            continue  # unrecognized family — namespace check still applies
        low, high = rng
        for entry in entries:
            num = entry.get("trial_number")
            if num is None:
                continue
            if not (low <= num <= high):
                errors.append(
                    f"RANGE VIOLATION: trial #{num} in '{name}' (family '{family}') "
                    f"is outside owned range {low}-{high} (TRIAL_ID_RANGES.md)"
                )
    return errors


def _normalize_slug(s: str) -> str:
    """Collapse a filename slug or ledger id down to bare alphanumerics for fuzzy
    matching (trial_7001_btc_vol_divergence.md's 'btc_vol_divergence' vs a ledger
    id of 'BTCVD-BTC-VOL-DIVERGENCE' or 'btc_vol_divergence' should all compare
    equal)."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def scan_pre_registration_docs(research_dir: Path) -> list[dict]:
    """Extract (trial_number, slug, family) from every pre_registration*/trial_NNNN_*.md
    filename. `family` mirrors trial_family(): '' for research/pre_registration/,
    '_c' for research/pre_registration_c/, etc. Non-numbered files (e.g. template.md)
    are skipped."""
    pattern = re.compile(r"^trial_(\d+)_(.+)\.md$")
    entries = []
    for md_path in sorted(research_dir.glob("pre_registration*/trial_*.md")):
        m = pattern.match(md_path.name)
        if not m:
            continue
        fam_m = re.match(r"pre_registration(_[a-z0-9]+)?$", md_path.parent.name)
        family = (fam_m.group(1) or "") if fam_m else md_path.parent.name
        entries.append(
            {
                "trial_number": int(m.group(1)),
                "slug": m.group(2),
                "family": family,
                "source": f"{md_path.parent.name}/{md_path.name}",
            }
        )
    return entries


def check_doc_numbers_exist(doc_entries: list[dict], ledger_pairs: list[tuple[str, list[dict]]]) -> list[str]:
    """Flag a pre_registration doc only when its family's ledger/registry already
    has an entry for the SAME trial (matched by normalized id/slug) under a
    DIFFERENT number than the doc's filename claims -- this is the #3001-vs-#3004
    bug class: a doc's filename disagreeing with the number its own ledger entry
    actually uses. A doc whose slug has no match anywhere in its family is treated
    as not-yet-resulted (e.g. status: PENDING, registered but no ledger entry yet)
    and is NOT an error -- that's the normal lifecycle, not a bug."""
    numbers_by_family: dict[str, set[int]] = defaultdict(set)
    slugs_by_family: dict[str, dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
    for name, entries in ledger_pairs:
        family = trial_family(name)
        for entry in entries:
            num = entry.get("trial_number")
            if num is None:
                continue
            numbers_by_family[family].add(num)
            entry_id = entry.get("id")
            if entry_id:
                slugs_by_family[family][_normalize_slug(str(entry_id))].add(num)

    errors = []
    for doc in doc_entries:
        family = doc["family"]
        if doc["trial_number"] in numbers_by_family.get(family, set()):
            continue
        doc_slug = _normalize_slug(doc["slug"])
        matches = {
            num
            for slug, nums in slugs_by_family.get(family, {}).items()
            for num in nums
            if doc_slug == slug or doc_slug in slug or slug in doc_slug
        }
        if matches:
            fam_label = family.lstrip("_") or "main"
            errors.append(
                f"DOC NUMBER MISMATCH: {doc['source']} filename says #{doc['trial_number']} "
                f"but family '{fam_label}' ledger/registry has this trial under "
                f"#{sorted(matches)} instead"
            )
    return errors


def check_mechanism(entries: list[dict]) -> list[str]:
    """Every trial entry should declare a 'mechanism' field distinguishing e.g.
    'single_asset_absolute_momentum' from 'cross_sectional_relative_momentum'.
    GATED (--mechanism): not every source file has 'mechanism' data yet.
    As of this writing (verified by grep, not assumed): trial_ledger.json and
    trial_ledger_b.json have none; trial_ledger_c.json has it on all 3 of its
    entries. hypothesis_registry_b.json and _e.json have none; main (9),
    _c (3), _d (3), and _f (1) do. Entries from files with real 'mechanism'
    data are correctly checked once loaded (load_ledger/load_registry both
    extract it); entries from files with none will always fail here until
    that source file is backfilled -- that's real missing data, not a loader
    bug. This is opt-in until 'mechanism' data covers every source file.
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

    errors.extend(check_family_range_ownership(ledger_pairs))

    doc_entries = scan_pre_registration_docs(RESEARCH_DIR)
    errors.extend(check_doc_numbers_exist(doc_entries, ledger_pairs))

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

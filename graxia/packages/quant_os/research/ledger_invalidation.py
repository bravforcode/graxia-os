"""Trial-ledger / hypothesis-registry invalidation on cost-basis change (Phase 1).

When a symbol is demoted, every trial in research/trial_ledger.json and every
hypothesis in research/hypothesis_registry*.json that referenced the symbol
while it was tradeable gets an appended note — never a deletion:
  "provenance_invalidated": true,
  "provenance_invalidation": {symbol, reason, audit_ref, invalidated_at_utc}

This is the same keep-for-the-record pattern used for trial #1029/#1030,
applied automatically. Idempotent: already-invalidated entries are skipped.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path

RESEARCH_DIR = Path(__file__).resolve().parent
TRIAL_LEDGER_PATH = RESEARCH_DIR / "trial_ledger.json"
HYPOTHESIS_REGISTRY_GLOB = "hypothesis_registry*.json"

_SYMBOL_TOKEN_RE = re.compile(r"[A-Z0-9]{2,12}")


def _entry_references_symbol(entry: dict, symbol: str) -> bool:
    """Heuristic cross-reference: the symbol appears in the entry's
    instrument string, universe list, data_sources, or note."""
    haystack: list[str] = []
    if isinstance(entry.get("instrument"), str):
        haystack.append(entry["instrument"])
    if isinstance(entry.get("note"), str):
        haystack.append(entry["note"])
    if isinstance(entry.get("universe"), list):
        haystack.extend(str(u) for u in entry["universe"])
    if isinstance(entry.get("data_sources"), list):
        haystack.extend(str(d) for d in entry["data_sources"])
    text = " ".join(haystack)
    return symbol in _SYMBOL_TOKEN_RE.findall(text.upper())


def _mark_entry(entry: dict, symbol: str, reason: str, audit_ref: str) -> bool:
    if entry.get("provenance_invalidated") is True:
        return False
    entry["provenance_invalidated"] = True
    entry["provenance_invalidation"] = {
        "symbol": symbol,
        "reason": reason,
        "audit_ref": audit_ref,
        "invalidated_at_utc": datetime.now(UTC).isoformat(),
    }
    return True


def invalidate_ledger(
    ledger: dict,
    symbol: str,
    reason: str,
    audit_ref: str,
) -> int:
    """Mark every lineage entry that references the symbol. Returns count."""
    count = 0
    for entry in ledger.get("lineage", []):
        if _entry_references_symbol(entry, symbol) and _mark_entry(entry, symbol, reason, audit_ref):
            count += 1
    return count


def invalidate_hypothesis_registry(
    registry: dict,
    symbol: str,
    reason: str,
    audit_ref: str,
) -> int:
    """Mark every hypothesis entry that references the symbol. Returns count."""
    count = 0
    for entry in registry.get("hypotheses", []):
        if _entry_references_symbol(entry, symbol) and _mark_entry(entry, symbol, reason, audit_ref):
            count += 1
    return count


def _atomic_write_json(path: Path, payload: dict) -> None:
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".ledger_", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, str(path))


def invalidate_symbol(
    symbol: str,
    *,
    reason: str,
    audit_ref: str,
    trial_ledger_path: str | Path = TRIAL_LEDGER_PATH,
    research_dir: str | Path = RESEARCH_DIR,
) -> dict:
    """Cross-reference one demoted symbol against the trial ledger and every
    hypothesis registry file. Append-only and idempotent.

    Returns {"trial_ledger_marked": int, "hypothesis_entries_marked": int,
             "files_written": [paths]}.
    """
    results: dict = {"trial_ledger_marked": 0, "hypothesis_entries_marked": 0, "files_written": []}

    ledger_path = Path(trial_ledger_path)
    if ledger_path.exists():
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        marked = invalidate_ledger(ledger, symbol, reason, audit_ref)
        if marked:
            _atomic_write_json(ledger_path, ledger)
            results["trial_ledger_marked"] = marked
            results["files_written"].append(str(ledger_path))

    for registry_path in sorted(Path(research_dir).glob(HYPOTHESIS_REGISTRY_GLOB)):
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        marked = invalidate_hypothesis_registry(registry, symbol, reason, audit_ref)
        if marked:
            _atomic_write_json(registry_path, registry)
            results["hypothesis_entries_marked"] += marked
            results["files_written"].append(str(registry_path))

    return results

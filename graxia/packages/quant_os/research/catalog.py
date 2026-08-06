"""Raw entry catalog for Direction I mining (spec §5 P1).

Every entry requires a source_url (no-fabrication rule). Partition
tagging (research/partition_registry) happens at ingest so taxonomy
never recommends Direction-H-owned families. No returns evaluated here
-> 0 N (spec §3.2).
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from research.partition_registry import check_partition

CATALOG_DIR = Path(__file__).resolve().parent / "catalog_i"

REQUIRED_FIELDS = [
    "name",
    "source",
    "source_url",
    "mechanism",
    "symbol",
    "timeframe",
    "params",
    "claimed_perf",
    "evidence_tier",
]
EVIDENCE_TIERS = ["literature", "myfxbook_verified", "practitioner"]


def validate_entry(entry: dict) -> list[str]:
    errors = []
    for f in REQUIRED_FIELDS:
        if f not in entry or entry[f] in (None, ""):
            errors.append(f"missing required field: {f}")
    if entry.get("source_url") and not str(entry["source_url"]).startswith(("http://", "https://")):
        errors.append("source_url must be an absolute http(s) URL")
    if entry.get("evidence_tier") not in EVIDENCE_TIERS:
        errors.append(f"evidence_tier must be one of {EVIDENCE_TIERS}")
    return errors


def _partition_tag(entry: dict) -> dict:
    r = check_partition(entry.get("mechanism", ""), entry.get("symbol", ""), entry.get("timeframe", ""))
    return {"status": r["status"], "owner": r["owner"], "note": r["note"]}


def load_entries(catalog_path: str | Path) -> list[dict]:
    path = Path(catalog_path)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("entries", [])
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"unreadable catalog {path}: {exc} — fail-closed") from exc


def _write(catalog_path: Path, entries: list[dict]) -> None:
    catalog_path.write_text(
        json.dumps({"schema_version": "1.0", "direction": "I", "entries": entries}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )


def add_entry(catalog_path: str | Path, entry: dict) -> dict:
    errors = validate_entry(entry)
    if errors:
        raise ValueError("; ".join(errors))
    path = Path(catalog_path)
    entries = load_entries(path)
    stamped = {
        **entry,
        "catalog_id": uuid.uuid4().hex[:12],
        "ingested_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "partition": _partition_tag(entry),
    }
    entries.append(stamped)
    _write(path, entries)
    return stamped


def ingest_batch(catalog_path: str | Path, entries: list[dict]) -> tuple[int, list[str]]:
    path = Path(catalog_path)
    existing = load_entries(path)
    added = 0
    errors = []
    for entry in entries:
        errs = validate_entry(entry)
        if errs:
            errors.append(f"{entry.get('name', '<unnamed>')}: {'; '.join(errs)}")
            continue
        existing.append(
            {
                **entry,
                "catalog_id": uuid.uuid4().hex[:12],
                "ingested_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
                "partition": _partition_tag(entry),
            }
        )
        added += 1
    _write(path, existing)
    return added, errors

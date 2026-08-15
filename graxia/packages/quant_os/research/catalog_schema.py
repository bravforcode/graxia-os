"""Direction I P1 catalog schema — entry contract for the deep-research harness.

Every mining entry MUST satisfy the P1 contract (spec §P1, A7, A17):
  - source_url is MANDATORY (no fabrication — a mined entry without a URL is rejected)
  - mechanism / params / claimed_perf / evidence_tier are required metadata
  - evidence_tier is one of LITERATURE / MYFXBOOK_VERIFIED / PRACTITIONER_LORE
  - partition_tag is stamped at ingest via partition_registry.check_partition()
    (OWNED_BY_H families must never be recommended downstream without structural
    justification — A17)

hash dedup mirrors research/screening_registry.py so P2 taxonomy can rely on
stable identity and N accounting stays clean.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from .partition_registry import check_partition

# Evidence tiers — spec §P3 (Evidence Triage)
EVIDENCE_TIERS = ("LITERATURE", "MYFXBOOK_VERIFIED", "PRACTITIONER_LORE")

# Valid P1 source ids (spec §P1 table)
SOURCE_IDS = ("S1", "S2", "S3", "S4", "S5", "S6")

CATALOG_DIR = Path(__file__).resolve().parent / "catalog_i"

REQUIRED_FIELDS = ("source_url", "mechanism", "claimed_perf", "evidence_tier")


def entry_hash(source_id: str, source_url: str, mechanism: str, params: dict) -> str:
    """Deterministic identity for a mined entry.

    Two entries with the same source + URL + mechanism + params are the same
    raw finding — never double-counted in the catalog.
    """
    canonical = "|".join(
        [source_id, source_url, mechanism.lower().replace(" ", "_"), json.dumps(params, sort_keys=True)]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_entry(entry: dict) -> list[str]:
    """Return a list of contract violations. Empty list = entry is valid.

    Rules (spec §P1: "Every entry must have source URL + metadata. No fabrication."):
      1. source_id must be a known P1 source
      2. source_url must be present, non-empty, and an http(s) URL
      3. required metadata fields present and non-empty
      4. evidence_tier must be one of the three tiers
      5. claimed_perf must not contain placeholder/hype tokens (no fabricated numbers)
      6. mechanism must not be a generic "unknown"/"n/a" placeholder
    """
    errors: list[str] = []

    source_id = entry.get("source_id", "")
    if source_id not in SOURCE_IDS:
        errors.append(f"invalid source_id: {source_id!r} (must be one of {SOURCE_IDS})")

    url = entry.get("source_url", "")
    if not url or not isinstance(url, str):
        errors.append("source_url missing (mandatory — no fabrication)")
    elif not (url.startswith("http://") or url.startswith("https://")):
        errors.append(f"source_url must be http(s): {url!r}")

    for field in REQUIRED_FIELDS:
        value = entry.get(field)
        if not value or not isinstance(value, str):
            errors.append(f"missing required field: {field}")

    tier = entry.get("evidence_tier")
    if tier and tier not in EVIDENCE_TIERS:
        errors.append(f"invalid evidence_tier: {tier!r} (must be one of {EVIDENCE_TIERS})")

    # Placeholder / fabrication markers — a real mined entry carries real data.
    perf = str(entry.get("claimed_perf", "")).lower()
    for token in ("tbd", "todo", "placeholder", "unknown", "n/a", "lorem", "xxx", "example"):
        if token in perf:
            errors.append(f"claimed_perf contains placeholder token: {token!r}")
            break

    mechanism = str(entry.get("mechanism", "")).lower()
    if mechanism in ("", "unknown", "n/a", "todo", "tbd"):
        errors.append("mechanism missing or placeholder")

    return errors


def stamp_partition(entry: dict) -> dict:
    """Apply the A17 partition tag at ingest using partition_registry.

    Returns a new dict with partition_tag / partition_owner / partition_note
    populated. FREE entries carry partition_tag="FREE".
    """
    mechanism = str(entry.get("mechanism", ""))
    symbol = str(entry.get("symbol", ""))
    timeframe = str(entry.get("timeframe", ""))
    result = check_partition(mechanism, symbol, timeframe)
    stamped = dict(entry)
    stamped["partition_tag"] = result["status"]
    stamped["partition_owner"] = result["owner"]
    stamped["partition_note"] = result["note"]
    return stamped


def finalize_entry(entry: dict, *, source_id: str) -> dict:
    """Validate + stamp + hash an incoming raw entry into a catalog record.

    Raises ValueError on contract violation — the mining runner must NOT write
    fabricated/placeholder entries into the catalog.
    """
    raw = dict(entry)
    raw.setdefault("source_id", source_id)
    errors = validate_entry(raw)
    if errors:
        raise ValueError("; ".join(errors))

    raw.setdefault("params", {})
    raw.setdefault("symbol", "")
    raw.setdefault("timeframe", "")
    raw["hash"] = entry_hash(raw["source_id"], raw["source_url"], raw["mechanism"], raw.get("params", {}))
    raw["ingested_at"] = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    return stamp_partition(raw)


def load_raw(source_id: str, catalog_dir: str | Path = CATALOG_DIR) -> list[dict]:
    """Load entries from research/catalog_i/raw_<source>.json (empty if absent)."""
    path = Path(catalog_dir) / f"raw_{source_id}.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = data.get("entries", []) if isinstance(data, dict) else []
        return [e for e in entries if isinstance(e, dict)]
    except (json.JSONDecodeError, OSError):
        return []


def write_raw(source_id: str, entries: list[dict], catalog_dir: str | Path = CATALOG_DIR) -> Path:
    """Atomically write entries for one source. Keeps the catalog append-only:
    existing entries are preserved, new entries are deduped by hash.
    """
    catalog = Path(catalog_dir)
    catalog.mkdir(parents=True, exist_ok=True)
    existing = load_raw(source_id, catalog)
    seen = {e["hash"] for e in existing if "hash" in e}
    merged = list(existing)
    added = 0
    for entry in entries:
        h = entry.get("hash")
        if h in seen:
            continue
        seen.add(h)
        merged.append(entry)
        added += 1
    path = catalog / f"raw_{source_id}.json"
    payload = {
        "schema_version": "1.0",
        "source_id": source_id,
        "entries": merged,
        "count": len(merged),
        "written_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def catalog_stats(catalog_dir: str | Path = CATALOG_DIR) -> dict[str, object]:
    """Per-source counts + total for progress tracking against the 2,500 target."""
    catalog = Path(catalog_dir)
    per_source: dict[str, int] = {}
    if catalog.exists():
        for source in SOURCE_IDS:
            per_source[source] = len(load_raw(source, catalog))
    stats: dict[str, object] = {
        "total": sum(per_source.values()),
        "per_source": per_source,
    }
    return stats

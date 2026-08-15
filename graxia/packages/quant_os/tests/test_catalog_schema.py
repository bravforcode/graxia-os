# tests/test_catalog_schema.py
"""P1 catalog contract tests — no fabrication, URL mandatory, dedup, partition."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.catalog_schema import (  # noqa: E402
    EVIDENCE_TIERS,
    SOURCE_IDS,
    entry_hash,
    finalize_entry,
    validate_entry,
)


def _valid_entry() -> dict:
    return {
        "source_id": "S1",
        "name": "Test Grid EA",
        "source_url": "https://www.mql5.com/en/code/12345",
        "mechanism": "grid_martingale",
        "params": {"grid_spacing": 30, "multiplier": 2.0},
        "claimed_perf": "+25% in 6 months, 30% max DD (source claim)",
        "evidence_tier": "PRACTITIONER_LORE",
        "symbol": "EURUSD",
        "timeframe": "M15",
    }


def test_valid_entry_passes():
    assert validate_entry(_valid_entry()) == []


def test_missing_url_rejected():
    entry = _valid_entry()
    entry["source_url"] = ""
    errors = validate_entry(entry)
    assert any("source_url" in e for e in errors)


def test_non_http_url_rejected():
    entry = _valid_entry()
    entry["source_url"] = "ftp://example.com/ea"
    errors = validate_entry(entry)
    assert any("http" in e for e in errors)


def test_fabricated_claimed_perf_rejected():
    entry = _valid_entry()
    entry["claimed_perf"] = "TBD"
    errors = validate_entry(entry)
    assert any("placeholder" in e for e in errors)


def test_placeholder_mechanism_rejected():
    entry = _valid_entry()
    entry["mechanism"] = "unknown"
    errors = validate_entry(entry)
    assert any("mechanism" in e for e in errors)


def test_invalid_evidence_tier_rejected():
    entry = _valid_entry()
    entry["evidence_tier"] = "SPECULATION"
    errors = validate_entry(entry)
    assert any("evidence_tier" in e for e in errors)


def test_invalid_source_id_rejected():
    entry = _valid_entry()
    entry["source_id"] = "S99"
    errors = validate_entry(entry)
    assert any("source_id" in e for e in errors)


def test_entry_hash_stable_and_distinct():
    a = _valid_entry()
    b = _valid_entry()
    assert entry_hash(a["source_id"], a["source_url"], a["mechanism"], a["params"]) == entry_hash(
        b["source_id"], b["source_url"], b["mechanism"], b["params"]
    )
    # different URL -> different hash
    b["source_url"] = "https://www.mql5.com/en/code/99999"
    assert entry_hash(a["source_id"], a["source_url"], a["mechanism"], a["params"]) != entry_hash(
        b["source_id"], b["source_url"], b["mechanism"], b["params"]
    )


def test_finalize_stamps_hash_partition_and_timestamp():
    out = finalize_entry(_valid_entry(), source_id="S1")
    assert out["hash"]
    assert out["ingested_at"]
    assert out["partition_tag"] in ("FREE", "CLOSED", "WATCH")


def test_owned_by_h_partition_stamped_at_ingest():
    # forex4 H1 trend-continuity is CLOSED / OWNED_BY_H (A17)
    entry = _valid_entry()
    entry["mechanism"] = "trend_continuity"
    entry["symbol"] = "USDCAD"
    entry["timeframe"] = "H1"
    out = finalize_entry(entry, source_id="S1")
    assert out["partition_tag"] == "CLOSED"
    assert out["partition_owner"] == "H"


def test_evidence_tiers_and_sources_are_frozen():
    assert EVIDENCE_TIERS == ("LITERATURE", "MYFXBOOK_VERIFIED", "PRACTITIONER_LORE")
    assert SOURCE_IDS == ("S1", "S2", "S3", "S4", "S5", "S6")

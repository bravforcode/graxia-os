# tests/test_catalog.py
import json
import tempfile
from pathlib import Path

import pytest

from research.catalog import add_entry, ingest_batch, load_entries, validate_entry

SAMPLE = Path(__file__).resolve().parent / "fixtures" / "mining_sample.json"


def _entry(overrides=None):
    e = {
        "name": "Test EA",
        "source": "mql5",
        "source_url": "https://www.mql5.com/en/code/12345",
        "mechanism": "grid_martingale",
        "symbol": "XAUUSD",
        "timeframe": "H1",
        "params": {"grid_size": 50},
        "claimed_perf": "Sharpe 3.0",
        "evidence_tier": "practitioner",
    }
    if overrides:
        e.update(overrides)
    return e


def tmp_catalog():
    return str(Path(tempfile.mkdtemp()) / "catalog.json")


def test_validate_entry_ok():
    assert validate_entry(_entry()) == []


def test_validate_entry_requires_source_url():
    errs = validate_entry(_entry({"source_url": ""}))
    assert any("source_url" in e for e in errs)


def test_validate_entry_requires_evidence_tier_enum():
    errs = validate_entry(_entry({"evidence_tier": "magic"}))
    assert any("evidence_tier" in e for e in errs)


def test_add_entry_partition_tags_forex4_trend():
    p = tmp_catalog()
    entry = add_entry(p, _entry({"mechanism": "trend_continuity", "symbol": "USDCAD", "timeframe": "H1"}))
    assert entry["partition"]["status"] == "CLOSED"
    assert entry["partition"]["owner"] == "H"


def test_add_entry_rejects_no_url():
    p = tmp_catalog()
    with pytest.raises(ValueError):
        add_entry(p, _entry({"source_url": ""}))


def test_ingest_batch_returns_counts(tmp_path):
    entries = json.loads(SAMPLE.read_text(encoding="utf-8"))["entries"]
    p = tmp_path / "catalog.json"
    added, errs = ingest_batch(str(p), entries)
    assert added == len(entries)
    assert errs == []
    assert len(load_entries(str(p))) == len(entries)


def test_contract_matches_module():
    contract = json.loads(
        (Path(__file__).resolve().parents[1] / "research" / "catalog_i" / "contract_v1.json").read_text(
            encoding="utf-8"
        )
    )
    for f in contract["required_fields"]:
        assert f in {
            "name",
            "source",
            "source_url",
            "mechanism",
            "symbol",
            "timeframe",
            "params",
            "claimed_perf",
            "evidence_tier",
        }
    assert contract["evidence_tiers"] == ["literature", "myfxbook_verified", "practitioner"]

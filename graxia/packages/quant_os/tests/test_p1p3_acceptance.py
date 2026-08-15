# tests/test_p1p3_acceptance.py
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_canonical_artifact_exists():
    canon = json.loads((ROOT / "research" / "catalog_i" / "canonical_mechanisms.json").read_text(encoding="utf-8"))
    assert len(canon["canonical"]) >= 1


def test_shortlist_artifact_exists():
    sl = json.loads((ROOT / "research" / "catalog_i" / "shortlist.json").read_text(encoding="utf-8"))
    assert "shortlist" in sl


def test_no_partition_closed_in_shortlist():
    sl = json.loads((ROOT / "research" / "catalog_i" / "shortlist.json").read_text(encoding="utf-8"))
    for e in sl["shortlist"]:
        assert e.get("partition", {}).get("status") != "CLOSED"

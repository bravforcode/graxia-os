"""Schema tests for config/tradeable_universe.json (Phase 1 migration).

Pins the new arrays exist, the tradeable bar is untouched, and the loader
contract in scripts/select_tradeable_instruments.py keeps working.
"""

from __future__ import annotations

import json
from pathlib import Path

UNIVERSE_PATH = Path(__file__).resolve().parent.parent / "config" / "tradeable_universe.json"


def _universe() -> dict:
    return json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))


def test_schema_has_all_status_arrays():
    uni = _universe()
    for key in ("tradeable", "measuring", "verifying", "candidate", "excluded"):
        assert key in uni, f"missing top-level array: {key}"
        assert isinstance(uni[key], list), f"{key} must be a list"


def test_tradeable_entries_unchanged_shape():
    uni = _universe()
    for entry in uni["tradeable"]:
        assert "symbol" in entry
        assert "asset_class" in entry
        assert "cost_status" in entry
        assert "cost_evidence" in entry


def test_no_symbol_appears_in_two_arrays():
    uni = _universe()
    seen: set[str] = set()
    for key in ("tradeable", "measuring", "verifying", "candidate"):
        for entry in uni[key]:
            sym = entry["symbol"]
            assert sym not in seen, f"{sym} appears in multiple status arrays"
            seen.add(sym)


def test_version_bumped():
    assert _universe()["_meta"]["version"] == "1.2.0"

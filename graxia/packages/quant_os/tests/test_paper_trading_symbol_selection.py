"""
Tests for run_paper_trading.py's Phase 3 symbol-selection wiring.

The old default --symbols list (EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD,
USDCHF, NZDUSD, XAUUSD) was hardcoded and mostly disjoint from Phase 2C's
cost-verified universe (config/tradeable_universe.json). These tests lock
down the replacement: --symbols omitted now requires
config/selected_instruments.json (the Phase 3 selection layer's output),
and fails closed -- no silent fallback to any hardcoded list -- when that
artifact is missing or selected nothing.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "run_paper_trading.py"
_SPEC = importlib.util.spec_from_file_location("run_paper_trading", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_run_paper_trading = importlib.util.module_from_spec(_SPEC)
sys.modules["run_paper_trading"] = _run_paper_trading
_SPEC.loader.exec_module(_run_paper_trading)

_load_selected_symbols = _run_paper_trading._load_selected_symbols


class TestLoadSelectedSymbols:
    def test_missing_artifact_returns_empty(self, tmp_path):
        missing = tmp_path / "selected_instruments.json"
        with patch.object(_run_paper_trading, "_SELECTED_INSTRUMENTS_PATH", missing):
            assert _load_selected_symbols() == []

    def test_artifact_with_selection_returns_symbols(self, tmp_path):
        artifact = tmp_path / "selected_instruments.json"
        artifact.write_text(json.dumps({"selected": ["XAUUSD", "NAS100"]}))
        with patch.object(_run_paper_trading, "_SELECTED_INSTRUMENTS_PATH", artifact):
            assert _load_selected_symbols() == ["XAUUSD", "NAS100"]

    def test_artifact_with_empty_selection_returns_empty(self, tmp_path):
        """No confirmed edge is a valid, honest outcome -- must not be
        silently upgraded into a nonempty symbol list."""
        artifact = tmp_path / "selected_instruments.json"
        artifact.write_text(json.dumps({"selected": []}))
        with patch.object(_run_paper_trading, "_SELECTED_INSTRUMENTS_PATH", artifact):
            assert _load_selected_symbols() == []

    def test_corrupt_artifact_returns_empty_not_raises(self, tmp_path):
        artifact = tmp_path / "selected_instruments.json"
        artifact.write_text("{not valid json")
        with patch.object(_run_paper_trading, "_SELECTED_INSTRUMENTS_PATH", artifact):
            assert _load_selected_symbols() == []

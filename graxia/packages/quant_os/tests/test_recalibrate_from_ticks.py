"""Tests for Task 15 — recalibrate_from_ticks (median spread bps from
real tick bid/ask). Loaded via importlib: the monorepo root ships its own
scripts/ package, so `import scripts.recalibrate_from_ticks` can resolve
to the wrong tree under pytest (same issue as test_run_backfill.py)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

_SPEC = importlib.util.spec_from_file_location(
    "recalibrate_mod", Path(__file__).resolve().parent.parent / "scripts" / "recalibrate_from_ticks.py"
)
assert _SPEC is not None and _SPEC.loader is not None
_MOD = importlib.util.module_from_spec(_SPEC)
sys.modules["recalibrate_mod"] = _MOD
_SPEC.loader.exec_module(_MOD)

recalibrate = _MOD.recalibrate


def test_recalibrate_median_spread_and_commission():
    df = pd.DataFrame(
        {
            "bid": [100.0, 100.0, 100.0],
            "ask": [100.1, 100.2, 100.1],
            "volume": [1.0, 1.0, 1.0],
        }
    )
    out = recalibrate("XAUUSD", df)
    # spread bps: (ask-bid)/mid*10000 → 9.995, 19.98, 9.995 → median ~9.995
    assert abs(out["spread_bps"] - 9.995) < 0.01
    assert out["status"] == "FROM_TICKS"

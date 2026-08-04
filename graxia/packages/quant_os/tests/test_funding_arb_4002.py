"""Tests for Task 16 — Trial #4002 funding-arb stats (fixture funding rows,
importlib-loaded: monorepo root ships its own scripts/ package)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

_SPEC = importlib.util.spec_from_file_location(
    "funding_arb_mod", Path(__file__).resolve().parent.parent / "scripts" / "run_funding_arb_4002.py"
)
assert _SPEC is not None and _SPEC.loader is not None
_MOD = importlib.util.module_from_spec(_SPEC)
sys.modules["funding_arb_mod"] = _MOD
_SPEC.loader.exec_module(_MOD)

compute_funding_arb_stats = _MOD.compute_funding_arb_stats


def test_funding_stats_annualized():
    # 8h funding 0.0001 (1 bps) per period → ~10.95% annualized at 3 periods/day
    df = pd.DataFrame(
        {
            "timestamp_utc": ["2026-08-01T00:00:00Z", "2026-08-01T08:00:00Z", "2026-08-01T16:00:00Z"],
            "funding_rate": [0.0001, 0.0001, 0.0001],
            "mark_price": [100.0, 100.0, 100.0],
        }
    )
    stats = compute_funding_arb_stats(df)
    assert stats["n_periods"] == 3
    assert stats["positive_share"] == 1.0
    # 3 periods/day × 365d × 1bp (0.0001) = 1095 bps annualized
    assert abs(stats["annualized_yield_bps"] - 1095) < 10

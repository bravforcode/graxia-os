#!/usr/bin/env python3
"""Trial #4002 — Funding-Rate Arbitrage signal feasibility (pre-registered)."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LEDGER = ROOT / "research" / "trial_ledger.json"


def compute_funding_arb_stats(df: pd.DataFrame) -> dict:
    if df is None or len(df) == 0:
        raise ValueError("no funding data")
    rates = df["funding_rate"].astype(float)
    positive = float((rates > 0).mean())
    annualized = float(rates.mean() * 3 * 365 * 10_000)  # 3 periods/day, bps
    return {
        "n_periods": int(len(df)),
        "mean_funding_8h": float(rates.mean()),
        "annualized_yield_bps": annualized,
        "positive_share": positive,
        "first_ts": str(df["timestamp_utc"].min()),
        "last_ts": str(df["timestamp_utc"].max()),
    }


def main() -> int:
    from data_pipeline.storage.duckdb_store import DuckDBStore

    store = DuckDBStore()
    store.register_tick_views(
        backfill_globs={
            "binance_funding": "data/backfill/binance_funding/*.parquet",
        }
    )
    try:
        df = store.query_funding("BTCUSDT", 0, 10**18)
    except Exception:
        df = None
    if df is None or len(df) == 0:
        print("[4002] no funding data — run backfill first (phase 3).")
        return 0
    stats = compute_funding_arb_stats(df)
    print(
        f"[4002] periods={stats['n_periods']} mean8h={stats['mean_funding_8h']:.6f} "
        f"annualized_bps={stats['annualized_yield_bps']:.1f} positive_share={stats['positive_share']:.2%}"
    )
    ledger = json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else {"lineage": []}
    ledger.setdefault("lineage", []).append(
        {
            "trial_id": "4002",
            "strategy": "funding_arb",
            "status": "EXPLORATORY",
            "stats": stats,
            "run_at": datetime.now(UTC).isoformat(),
        }
    )
    tmp = LEDGER.with_suffix(".tmp")
    tmp.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    tmp.replace(LEDGER)
    print("[4002] ledger updated (lineage key). EXPLORATORY — not live-ready proof.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

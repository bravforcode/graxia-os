#!/usr/bin/env python3
"""Re-derive FROM_TICKS cost calibration from stored tick data (live + backfill)."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

COST_PATH = ROOT / "config" / "cost_calibration.json"


def recalibrate(symbol: str, ticks: pd.DataFrame) -> dict:
    if ticks is None or len(ticks) == 0:
        raise ValueError(f"no tick data for {symbol}")
    # Filter to real quotes only: MT5 COPY_TICKS_ALL mixes last-trade ticks
    # (bid==ask) with quote ticks. Zero-spread rows are NOT quotes — exclude.
    ticks = ticks[ticks["ask"] > ticks["bid"]]
    if len(ticks) == 0:
        raise ValueError(f"no quote ticks (ask>bid) for {symbol}")
    mid = (ticks["bid"] + ticks["ask"]) / 2.0
    spread_bps = ((ticks["ask"] - ticks["bid"]) / mid.replace(0, pd.NA) * 10_000.0).dropna()
    weight = ticks["volume"].fillna(1.0).clip(lower=1e-9)
    return {
        "symbol": symbol,
        "spread_bps": float(spread_bps.median()),
        "commission_bps": 0.0,  # commission is not in tick price — keep config value
        "status": "FROM_TICKS",
        "recalibrated_at": datetime.now(UTC).isoformat(),
    }


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".cost_", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, str(path))


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-derive cost calibration from tick parquet")
    parser.add_argument("--symbols", default="", help="comma-separated (default: all FROM_TICKS assets)")
    parser.add_argument("--days", type=int, default=30, help="lookback days per symbol")
    args = parser.parse_args()

    from data_pipeline.storage.duckdb_store import DuckDBStore

    store = DuckDBStore()
    store.register_tick_views()
    costs = json.loads(COST_PATH.read_text(encoding="utf-8"))
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()] or [
        sym for sym, rec in costs["assets"].items() if rec.get("status") == "FROM_TICKS"
    ]
    changed = 0
    for sym in symbols:
        end_msc = int(datetime.now(UTC).timestamp() * 1000)
        start_msc = end_msc - args.days * 86_400_000
        with contextlib.suppress(Exception):
            ticks = store.query_ticks(sym, start_msc, end_msc)
            if ticks is None or len(ticks) == 0:
                print(f"[recalibrate] {sym}: no tick data — skipping (config unchanged)")
                continue
            stats = recalibrate(sym, ticks)
            costs["assets"][sym]["spread_bps"] = stats["spread_bps"]
            costs["assets"][sym]["status"] = stats["status"]
            costs["assets"][sym]["recalibrated_at"] = stats["recalibrated_at"]
            changed += 1
            print(f"[recalibrate] {sym}: spread_bps={stats['spread_bps']:.3f}")
    if changed:
        _atomic_write_json(COST_PATH, costs)
        print(f"[recalibrate] updated {changed} asset(s) in {COST_PATH}")
    else:
        print("[recalibrate] nothing to update")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

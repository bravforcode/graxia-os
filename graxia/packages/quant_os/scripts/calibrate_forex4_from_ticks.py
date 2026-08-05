"""Calibrate FROM_TICKS cost entries for the 4 forex pairs (Direction H retest).

Reads the MT5 backfilled tick parquets (scripts/backfill_ticks_shortcut.py) for
USDCAD / USDCHF / AUDUSD / NZDUSD and writes full-schema entries into
config/cost_calibration.json — same pattern as
scripts/complete_cost_calibration_entries.py (BTCUSD/EURUSD). Atomic write.

Usage:
    python scripts/calibrate_forex4_from_ticks.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
COST_PATH = ROOT / "config" / "cost_calibration.json"
TICK_DIR = ROOT / "data" / "ticks"

# FX metadata mirrors the existing EURUSD/GBPUSD entries (Pepperstone Razor).
FX_META = {
    "USDCAD": {"commission_bps": 7.0, "contract_size": 100000.0, "tick_size": 1e-05},
    "USDCHF": {"commission_bps": 7.0, "contract_size": 100000.0, "tick_size": 1e-05},
    "AUDUSD": {"commission_bps": 7.0, "contract_size": 100000.0, "tick_size": 1e-05},
    "NZDUSD": {"commission_bps": 7.0, "contract_size": 100000.0, "tick_size": 1e-05},
}


def session_label(hour: int) -> str:
    if 0 <= hour < 7:
        return "asian"
    if 7 <= hour < 12:
        return "london"
    if 12 <= hour < 16:
        return "london_ny_overlap"
    if 16 <= hour < 22:
        return "ny"
    return "rollover"


def compute_sessions(df: pd.DataFrame) -> dict:
    quotes = df[df["ask"] > df["bid"]].copy()
    if len(quotes) == 0:
        return {}
    quotes["session"] = quotes["time"].dt.hour.map(session_label)
    mid = (quotes["bid"] + quotes["ask"]) / 2.0
    quotes["sbps"] = (quotes["ask"] - quotes["bid"]) / mid.replace(0, pd.NA) * 10_000.0
    out = {}
    for sess, g in quotes.groupby("session"):
        vals = g["sbps"].dropna()
        if len(vals) == 0:
            continue
        out[sess] = {
            "median": round(float(vals.median()), 4),
            "p90": round(float(vals.quantile(0.9)), 4),
            "n": int(len(vals)),
        }
    return out


def atomic_write(path: Path, data: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".cost_", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.flush()
    os.replace(tmp, str(path))


def main() -> None:
    costs = json.loads(COST_PATH.read_text(encoding="utf-8"))
    now = datetime.now(UTC)

    for sym, meta in FX_META.items():
        parquet = TICK_DIR / f"{sym}_ticks_backfill.parquet"
        if not parquet.exists():
            print(f"SKIP {sym}: no parquet")
            continue
        df = pd.read_parquet(parquet)
        quotes = df[df["ask"] > df["bid"]]
        if len(quotes) == 0:
            print(f"SKIP {sym}: no quote ticks (ask>bid)")
            continue
        mid = (quotes["bid"] + quotes["ask"]) / 2.0
        sbps = ((quotes["ask"] - quotes["bid"]) / mid.replace(0, pd.NA) * 10_000.0).dropna().astype(float)
        tmin, tmax = df["time"].min(), df["time"].max()
        duration_days = (tmax - tmin).total_seconds() / 86400.0
        comm = meta["commission_bps"]

        entry = costs["assets"].get(sym, {})
        entry.update(
            {
                "mt5_symbol": sym,
                "spread_bps_measured": float(sbps.median()),
                "spread_bps_p95": float(sbps.quantile(0.95)),
                "spread_bps_mean": float(sbps.mean()),
                "spread_bps_min": float(sbps.min()),
                "spread_bps_max": float(sbps.max()),
                "spread_bps_std": float(sbps.std()),
                "commission_bps": comm,
                "slippage_bps_measured": None,
                "round_trip_bps_measured": round(float(sbps.median()) * 2 + comm * 2, 6),
                "round_trip_bps_p95": round(float(sbps.quantile(0.95)) * 2 + comm * 2, 6),
                "contract_size": meta["contract_size"],
                "tick_size": meta["tick_size"],
                "status": "FROM_TICKS",
                "sample_size": int(len(quotes)),
                "measurement_window": f"{tmin.date()} -> {tmax.date()} (UTC)",
                "measurement_duration_days": round(duration_days, 2),
                "measurement_mode": "mt5_copy_ticks_range_backfill",
                "sessions": compute_sessions(df),
                "broker_source": "Pepperstone Razor (MT5)",
                "notes": "Direction H retest cost calibration — backfilled via mt5.copy_ticks_range. "
                "Filtered to ask>bid quote ticks (MT5 COPY_TICKS_ALL mixes last-trade ticks). "
                "slippage: null; fill-simulator P90 is the source when measured.",
                "recalibrated_at": now.isoformat(),
            }
        )
        costs["assets"][sym] = entry
        print(
            f"{sym}: {entry['sample_size']:,} quote ticks, median {entry['spread_bps_measured']:.4f} bps, "
            f"window {entry['measurement_window']}"
        )

    atomic_write(COST_PATH, costs)
    print(f"Updated {COST_PATH}")


if __name__ == "__main__":
    main()

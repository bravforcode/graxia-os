"""Complete BTCUSD/EURUSD cost_calibration.json entries with tick metadata.

recalibrate_from_ticks.py only writes spread_bps/status/recalibrated_at.
This fills the full schema (sample_size, measurement_window, duration, mode,
sessions, notes, broker_source) from the backfilled tick parquet, matching the
richness of the original XAUUSD FROM_TICKS entry. Atomic write.

Usage:
    python scripts/complete_cost_calibration_entries.py
"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
COST_PATH = ROOT / "config" / "cost_calibration.json"
TICK_DIR = ROOT / "data" / "ticks"

SYMBOLS = {
    "BTCUSD": {"commission_bps": 10.0, "contract_size": 1.0, "tick_size": 0.01, "mt5_symbol": "BTCUSD"},
    "EURUSD": {"commission_bps": 7.0, "contract_size": 100000.0, "tick_size": 1e-05, "mt5_symbol": "EURUSD"},
}


# Session label by UTC hour (matching measure_spread_continuous.py's convention).
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
    """Per-session spread stats from quote ticks, matching the legacy schema:
    {session: {median, p90, n}}."""
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
    with open(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.flush()
    import os

    os.replace(tmp, str(path))


def main() -> None:
    costs = json.loads(COST_PATH.read_text(encoding="utf-8"))
    now = datetime.now(UTC)

    for sym, meta in SYMBOLS.items():
        parquet = TICK_DIR / f"{sym}_ticks_backfill.parquet"
        if not parquet.exists():
            print(f"SKIP {sym}: no parquet")
            continue
        df = pd.read_parquet(parquet)
        quotes = df[df["ask"] > df["bid"]]
        mid = (quotes["bid"] + quotes["ask"]) / 2.0
        sbps = ((quotes["ask"] - quotes["bid"]) / mid.replace(0, pd.NA) * 10_000.0).dropna()
        sbps_f = sbps.astype(float)
        tmin = df["time"].min()
        tmax = df["time"].max()
        duration_days = (tmax - tmin).total_seconds() / 86400.0

        entry = costs["assets"].get(sym, {})
        entry.update(
            {
                "mt5_symbol": meta["mt5_symbol"],
                "spread_bps_measured": float(sbps_f.median()),
                "spread_bps_p95": float(sbps_f.quantile(0.95)),
                "spread_bps_mean": float(sbps_f.mean()),
                "spread_bps_min": float(sbps_f.min()),
                "spread_bps_max": float(sbps_f.max()),
                "spread_bps_std": float(sbps_f.std()),
                "commission_bps": meta["commission_bps"],
                "slippage_bps_measured": None,  # honest: not measured from ticks; fill simulator P90 is the source
                "round_trip_bps_measured": float(sbps_f.median()) * 2 + float(str(meta["commission_bps"])) * 2,
                "round_trip_bps_p95": float(sbps_f.quantile(0.95)) * 2 + float(str(meta["commission_bps"])) * 2,
                "contract_size": meta["contract_size"],
                "tick_size": meta["tick_size"],
                "status": "FROM_TICKS",
                "sample_size": int(len(quotes)),
                "measurement_window": f"{tmin.date()} -> {tmax.date()} (UTC)",
                "measurement_duration_days": round(duration_days, 2),
                "measurement_mode": "mt5_copy_ticks_range_backfill",
                "sessions": compute_sessions(df),
                "broker_source": "Pepperstone Razor (MT5)",
                "notes": "Backfilled via mt5.copy_ticks_range (full tick history served by broker). "
                "EURUSD filtered to ask>bid quotes only (MT5 COPY_TICKS_ALL mixes last-trade ticks). "
                "Pending live 7-day sampling completion 2026-08-12 for confirmation.",
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

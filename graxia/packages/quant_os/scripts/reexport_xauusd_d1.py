"""
Re-export a single-convention XAUUSD D1 history from the live MT5 terminal.

Why: data/XAUUSD_D1.csv is contaminated with 2 bars/day (00:00 + 07:00
timestamps) — two different D1-close conventions concatenated. The provenance
loader (provenance.py:97-111) hard-fails on it. Per the WS-A trial-1028 review,
the fix is a clean re-export from an authoritative single source (MT5), NOT a
keep-one-drop-one patch (that would silently pick a convention).

Usage:
    python scripts/reexport_xauusd_d1.py        # needs running, logged-in MT5 terminal

Safety: backs up the existing CSV before overwriting; writes a provenance
manifest recording source + row count + dedup proof. Read-only MT5 access.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "data"
SRC_CSV = DATA_DIR / "XAUUSD_D1.csv"
SYMBOL = "XAUUSD"
TIMEFRAME = "D1"
START = datetime(2005, 1, 1, tzinfo=UTC)
MANIFEST = DATA_DIR / "XAUUSD_D1_provenance_manifest.json"


def main() -> int:
    import MetaTrader5 as mt5  # noqa: N813 – intentional alias for MT5 package

    print("[*] Initializing MT5 (connects to running terminal)...")
    if not mt5.initialize():
        print(f"[FAIL] mt5.initialize(): {mt5.last_error()}")
        print("       Open the MT5 terminal and log in to Pepperstone-Demo first.")
        return 1
    try:
        ti = mt5.terminal_info()
        if ti is None:
            print("[FAIL] no terminal info — terminal not running/logged in")
            return 1
        print(f"[OK] Terminal: {getattr(ti, 'path', 'n/a')}  server={getattr(ti, 'server', 'n/a')}")

        ai = mt5.account_info()
        if ai is None:
            print("[FAIL] not logged in — log into Pepperstone-Demo in the terminal first")
            return 1
        print(f"[OK] Logged in: login={ai.login} server={ai.server}")

        if not mt5.symbol_select(SYMBOL, True):
            print(f"[FAIL] symbol_select({SYMBOL}) failed: {mt5.last_error()}")
            return 1

        print(f"[*] Pulling {SYMBOL} {TIMEFRAME} from {START.date()} to now...")
        rates = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_D1, datetime(2005, 1, 1), datetime.now())
        if rates is None or len(rates) == 0:
            print(f"[FAIL] copy_rates_range returned {rates}: {mt5.last_error()}")
            return 1
        print(f"[OK] pulled {len(rates)} bars")

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.strftime("%Y-%m-%d %H:%M:%S")
        out = df[["time", "open", "high", "low", "close", "tick_volume"]].rename(columns={"tick_volume": "volume"})

        # Dedup proof: single-convention D1 must have exactly one bar per calendar day.
        norm = pd.to_datetime(out["time"]).dt.normalize()
        dup = len(norm) - norm.nunique()
        assert dup == 0, f"re-export still has {dup} duplicate-date bars — abort"
        assert out["high"].ge(out[["open", "close"]].max(axis=1)).all(), "invalid OHLC (high)"
        assert out["low"].le(out[["open", "close"]].min(axis=1)).all(), "invalid OHLC (low)"

        # Backup the contaminated file before overwriting.
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = DATA_DIR / f"XAUUSD_D1.csv.bak_{stamp}"
        if SRC_CSV.exists():
            backup.write_bytes(SRC_CSV.read_bytes())
            print(f"[OK] backed up contaminated file -> {backup.name}")

        out.to_csv(SRC_CSV, index=False)
        print(f"[OK] wrote clean single-convention D1 -> {SRC_CSV.name} ({len(out)} rows)")

        manifest = {
            "source": "MT5 live terminal (Pepperstone-Demo), copy_rates_range D1",
            "symbol": SYMBOL,
            "timeframe": TIMEFRAME,
            "start": START.date().isoformat(),
            "end": out["time"].iloc[-1],
            "rows": int(len(out)),
            "unique_dates": int(norm.nunique()),
            "duplicate_bars": int(dup),
            "min_year": int(pd.to_datetime(out["time"]).dt.year.min()),
            "generated_at": datetime.now(UTC).isoformat(),
            "script": "scripts/reexport_xauusd_d1.py",
            "backup": backup.name,
            "note": "Replaces 2-bars/day contaminated file with single-convention MT5 D1.",
        }
        MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"[OK] manifest -> {MANIFEST.name}")
        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    sys.exit(main())

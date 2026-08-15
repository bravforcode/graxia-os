"""
Re-export clean single-convention D1 history for all WS-A symbols from MT5.

Why: only XAUUSD was re-exported (trial 1028). The other 6 symbols still have
the original CSVs from an unknown source. This script re-exports them all from
the live MT5 terminal to ensure provenance-clean data for the full 2005-2026 range.

Usage:
    python scripts/reexport_all_symbols_d1.py        # needs running, logged-in MT5 terminal

Safety: backs up existing CSVs before overwriting; writes provenance manifests.
Read-only MT5 access.
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
START = datetime(2005, 1, 1, tzinfo=UTC)

SYMBOLS = ["XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100", "US30"]


def reexport_symbol(mt5, symbol: str) -> int:
    """Re-export a single symbol. Returns 0 on success, 1 on failure."""
    csv_path = DATA_DIR / f"{symbol}_D1.csv"
    manifest_path = DATA_DIR / f"{symbol}_D1_provenance_manifest.json"

    print(f"\n{'='*60}")
    print(f"  {symbol}")
    print(f"{'='*60}")

    if not mt5.symbol_select(symbol, True):
        print(f"[FAIL] symbol_select({symbol}) failed: {mt5.last_error()}")
        return 1

    print(f"[*] Pulling {symbol} D1 from {START.date()} to now...")
    rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_D1, START, datetime.now())
    if rates is None or len(rates) == 0:
        print(f"[FAIL] copy_rates_range returned {rates}: {mt5.last_error()}")
        return 1
    print(f"[OK] pulled {len(rates)} bars")

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    out = df[["time", "open", "high", "low", "close", "tick_volume"]].rename(
        columns={"tick_volume": "volume"}
    )

    # Dedup proof: single-convention D1 must have exactly one bar per calendar day.
    norm = pd.to_datetime(out["time"]).dt.normalize()
    dup = int(len(norm) - norm.nunique())
    assert dup == 0, f"{symbol}: re-export still has {dup} duplicate-date bars — abort"
    assert out["high"].ge(out[["open", "close"]].max(axis=1)).all(), (
        f"{symbol}: invalid OHLC (high)"
    )
    assert out["low"].le(out[["open", "close"]].min(axis=1)).all(), (
        f"{symbol}: invalid OHLC (low)"
    )

    # Backup the existing file before overwriting.
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = DATA_DIR / f"{symbol}_D1.csv.bak_{stamp}"
    if csv_path.exists():
        backup.write_bytes(csv_path.read_bytes())
        print(f"[OK] backed up -> {backup.name}")

    out.to_csv(csv_path, index=False)
    print(f"[OK] wrote clean single-convention D1 -> {csv_path.name} ({len(out)} rows)")

    manifest = {
        "source": "MT5 live terminal (Pepperstone-Demo), copy_rates_range D1",
        "symbol": symbol,
        "timeframe": "D1",
        "start": START.date().isoformat(),
        "end": out["time"].iloc[-1],
        "rows": int(len(out)),
        "unique_dates": int(norm.nunique()),
        "duplicate_bars": dup,
        "min_year": int(pd.to_datetime(out["time"]).dt.year.min()),
        "generated_at": datetime.now(UTC).isoformat(),
        "script": "scripts/reexport_all_symbols_d1.py",
        "backup": backup.name if csv_path.exists() else None,
        "note": "Re-exported from MT5 for provenance-clean single-convention D1.",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"[OK] manifest -> {manifest_path.name}")
    return 0


def main() -> int:
    import MetaTrader5 as mt5  # noqa: N813 – intentional alias

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

        failed = []
        for sym in SYMBOLS:
            rc = reexport_symbol(mt5, sym)
            if rc != 0:
                failed.append(sym)

        print(f"\n{'='*60}")
        if failed:
            print(f"[DONE] {len(SYMBOLS) - len(failed)}/{len(SYMBOLS)} succeeded, FAILED: {failed}")
            return 1
        else:
            print(f"[DONE] All {len(SYMBOLS)} symbols re-exported successfully.")
            return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    sys.exit(main())

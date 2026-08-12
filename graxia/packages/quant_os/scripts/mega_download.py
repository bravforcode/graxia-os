"""
mega_download.py — Single-process mega data downloader
======================================================
Scans MT5 for available symbols × timeframes, then downloads everything
in one process. Much faster than multi-subprocess approach.

Usage:
  python scripts/mega_download.py                    # full download
  python scripts/mega_download.py --quick             # M15/H1/D1 only  
  python scripts/mega_download.py --scan-only         # just scan availability
"""

import io, json, sys, time
from datetime import datetime, UTC
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

HERE = Path(__file__).resolve().parent
QUANT_OS = HERE.parent
DATA_DIR = QUANT_OS / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

import MetaTrader5 as mt5
import pandas as pd

# ─── Target universe ────────────────────────────────────────────────
TARGET_SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
    "XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD",
    "US30", "NAS100",
    "BTCUSD", "ETHUSD",
]

MT5_TIMEFRAMES = {
    "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1, "W1": mt5.TIMEFRAME_W1, "MN1": mt5.TIMEFRAME_MN1,
}

TF_MAX_BARS = {
    "M1": 100000, "M5": 100000, "M15": 60000, "M30": 50000,
    "H1": 50000, "H4": 25000, "D1": 5000, "W1": 2000, "MN1": 1000,
}


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def scan_available(quick: bool = False) -> dict:
    """Scan which symbols × timeframes are available in MT5 (quick: test 1 bar)."""
    log("Scanning MT5 for available symbols × timeframes...")
    available = {}
    mt5.initialize()

    test_tfs = ["M15", "H1", "D1"] if quick else list(MT5_TIMEFRAMES.keys())

    for sym in TARGET_SYMBOLS:
        info = mt5.symbol_info(sym)
        if info is None:
            log(f"  {sym}: NOT FOUND")
            continue

        # Ensure symbol is selectable
        selected = mt5.symbol_select(sym, True)
        if not selected:
            log(f"  {sym}: cannot select ({mt5.last_error()})")
            continue

        available_tfs = []
        for tf_name in test_tfs:
            tf_const = MT5_TIMEFRAMES[tf_name]
            rates = mt5.copy_rates_from_pos(sym, tf_const, 0, 5)
            if rates is not None and len(rates) > 0:
                last_close = rates[-1][4]
                if pd.notna(last_close) and last_close > 0:
                    available_tfs.append(tf_name)
            # silent skip for failures

        if available_tfs:
            available[sym] = available_tfs
            log(f"  {sym}: {len(available_tfs)} TFs → {', '.join(available_tfs)}")

    mt5.shutdown()
    return available


def download_all(available: dict = None, quick: bool = False) -> dict:
    """Download all symbols × timeframes in one MT5 session.
    If available is None, tries all TFs for all symbols directly (no scan)."""
    results = {"ok": 0, "fail": 0, "files": [], "total_bars": 0}
    mt5.initialize()

    target_tfs = ["M15", "H1", "D1"] if quick else list(MT5_TIMEFRAMES.keys())

    for sym in TARGET_SYMBOLS:
        if available and sym not in available:
            continue

        # Check symbol exists
        info = mt5.symbol_info(sym)
        if info is None:
            log(f"  {sym}: NOT FOUND, skipping")
            continue

        selected = mt5.symbol_select(sym, True)
        if not selected:
            log(f"  {sym}: cannot select, skipping")
            continue

        for tf_name in target_tfs:
            if available and tf_name not in available.get(sym, []):
                continue

            tf_const = MT5_TIMEFRAMES[tf_name]
            n_bars = TF_MAX_BARS[tf_name]
            csv_path = DATA_DIR / f"{sym}_{tf_name}.csv"

            # Skip if downloaded < 15 min ago
            if csv_path.exists() and time.time() - csv_path.stat().st_mtime < 900:
                results["ok"] += 1
                results["files"].append(f"{sym}_{tf_name}(cached)")
                continue

            rates = mt5.copy_rates_from_pos(sym, tf_const, 0, n_bars)
            if rates is None or len(rates) == 0:
                results["fail"] += 1
                continue

            df = pd.DataFrame(rates)
            if "time" in df.columns:
                df["time"] = pd.to_datetime(df["time"], unit="s").dt.strftime("%Y-%m-%d %H:%M:%S")
            cols_out = [c for c in ["time", "open", "high", "low", "close", "tick_volume"]
                       if c in df.columns]
            df = df[cols_out]
            if "tick_volume" in df.columns:
                df = df.rename(columns={"tick_volume": "volume"})

            df.to_csv(csv_path, index=False)
            results["ok"] += 1
            results["total_bars"] += len(df)
            first = df["time"].iloc[0] if "time" in df.columns else "?"
            last = df["time"].iloc[-1] if "time" in df.columns else "?"
            log(f"  {sym:6s} {tf_name:4s}: {len(df):>6,} bars  {first} → {last}")

    mt5.shutdown()
    return results


def save_scan(available: dict, elapsed: int):
    """Save scan manifest."""
    manifest = {
        "last_scan": datetime.now(UTC).isoformat(),
        "elapsed_seconds": elapsed,
        "symbols": {sym: tfs for sym, tfs in available.items()},
        "total_symbols": len(available),
        "total_tf_combos": sum(len(tfs) for tfs in available.values()),
    }
    meta_dir = QUANT_OS / "Meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "data_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log(f"Scan manifest saved ({manifest['total_tf_combos']} combos × {manifest['total_symbols']} symbols)")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Mega data downloader")
    parser.add_argument("--quick", action="store_true", help="M15/H1/D1 only")
    parser.add_argument("--scan-only", action="store_true", help="Scan only")
    parser.add_argument("--direct", action="store_true", help="Direct download without scan")
    args = parser.parse_args()

    t0 = time.time()

    if args.direct:
        # Skip scan — download directly (faster for known-good symbols)
        log(f"═══ DIRECT DOWNLOAD ({'QUICK' if args.quick else 'FULL'}) ═══")
        dl = download_all(available=None, quick=args.quick)
    else:
        # Phase 1: Scan
        log(f"═══ PHASE 1: SCAN ({'QUICK' if args.quick else 'FULL'}) ═══")
        available = scan_available(quick=args.quick)
        n_sym = len(available)
        n_tf = sum(len(tfs) for tfs in available.values())
        log(f"Scan done: {n_sym} symbols, {n_tf} TF combos in {time.time()-t0:.0f}s")
        save_scan(available, int(time.time() - t0))

        if args.scan_only:
            log("═══ Scan only — exiting ═══")
            return

        # Phase 2: Download
        log("═══ PHASE 2: DOWNLOAD ═══")
        dl = download_all(available, quick=args.quick)

    elapsed = int(time.time() - t0)
    log("═══ DONE ═══")
    log(f"Time: {elapsed}s | OK: {dl['ok']} | Fail: {dl['fail']} | Bars: {dl['total_bars']:,}")

    # Final summary
    csv_count = len(list(DATA_DIR.glob("*.csv")))
    total_size = sum(f.stat().st_size for f in DATA_DIR.glob("*.csv"))
    log(f"Data dir: {csv_count} CSVs, {total_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()

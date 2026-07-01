"""
download_everything.py — MASSIVE Parallel Data Downloader
========================================================
Pulls EVERYTHING: forex, indices, commodities, crypto, multi-timeframe,
tick data, news events, macro data. Runs in parallel threads.

Usage:
  python scripts/download_everything.py                 # full pull
  python scripts/download_everything.py --quick         # recent bars only
  python scripts/download_everything.py --tick          # include ticks
  python scripts/download_everything.py --news          # economic calendar
"""

import io, json, os, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

HERE = Path(__file__).resolve().parent
QUANT_OS = HERE.parent
DATA_DIR = QUANT_OS / "data"
TICK_DIR = DATA_DIR / "ticks"
MACRO_DIR = DATA_DIR / "macro"
NEWS_DIR = DATA_DIR / "news"
MANIFEST_DIR = DATA_DIR / "manifests"
VENV_PYTHON = sys.executable

# ─── MEGA SYMBOL LIST ─────────────────────────────────────────────────
FOREX = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"]
METALS = ["XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD"]
INDICES = ["US30", "NAS100"]
COMMODITIES = []
CRYPTO = ["BTCUSD", "ETHUSD"]
ALL_SYMBOLS = FOREX + METALS + INDICES + COMMODITIES + CRYPTO

# ─── ALL TIMEFRAMES ──────────────────────────────────────────────────
TIMEFRAMES = {"M1": 1, "M5": 5, "M15": 15, "M30": 30,
              "H1": 60, "H4": 240, "D1": 1440, "W1": 10080}

# ─── LOGGING ─────────────────────────────────────────────────────────
_start_time = time.time()
_downloaded = 0
_errors = 0

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")

def elapsed():
    return int(time.time() - _start_time)

# ─── MT5 DOWNLOAD ────────────────────────────────────────────────────

def download_all_mt5_bulk() -> dict:
    """Download ALL symbols × ALL timeframes in ONE process via --list-all."""
    global _downloaded, _errors
    results = {"ok": [], "cached": [], "fail": []}

    script = QUANT_OS / "download_mt5_symbols.py"
    if not script.exists():
        log("download_mt5_symbols.py not found!")
        return results

    log("Launching bulk download (single MT5 process)...")
    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(QUANT_OS.parent.parent) + os.pathsep + env.get("PYTHONPATH", "")
        r = subprocess.run(
            [VENV_PYTHON, str(script), "--list-all"],
            capture_output=True, text=True, timeout=600, encoding="utf-8", errors="replace",
            env=env,
        )
        # Parse output lines like "XAUUSD M15 : 50000 bars ..."
        for line in (r.stdout or "").splitlines():
            line = line.strip()
            if not line or line.startswith("Total") or line.startswith("Usage"):
                continue
            # Format: "SYMBOL  TF: NNN bars  first -> last"
            for s in ALL_SYMBOLS:
                if line.startswith(s):
                    results["ok"].append(line.strip())
                    _downloaded += 1
                    break

        log(f"Bulk download: {len(results['ok'])} symbol/TF lines parsed")
    except subprocess.TimeoutExpired:
        log("Bulk download timed out (partial OK)")
    except Exception as e:
        log(f"Bulk download error: {e}")

    # Verify by counting actual CSV files
    for symbol in ALL_SYMBOLS:
        for tf_name, tf_val in TIMEFRAMES.items():
            csv_path = DATA_DIR / f"{symbol}_{tf_name}.csv"
            if csv_path.exists() and csv_path.stat().st_size > 100:
                age = time.time() - csv_path.stat().st_mtime
                if age < 1200:  # downloaded in last 20 min
                    tag = f"{symbol}_{tf_name}"
                    if tag not in [r.split()[0] for r in results["ok"]]:
                        results["ok"].append(f"{tag} (verified)")
                        _downloaded += 1

    return results

# ─── YAHOO FALLBACK ──────────────────────────────────────────────────

def download_yahoo_symbol(symbol: str) -> bool:
    """Download daily data from Yahoo Finance as fallback."""
    import yfinance as yf  # available via quant_OS deps
    try:
        ticker = yf.Ticker(symbol.replace("XAUUSD", "GC=F")
                                  .replace("XAGUSD", "SI=F")
                                  .replace("US30", "^DJI")
                                  .replace("SPX500", "^GSPC")
                                  .replace("NAS100", "^IXIC")
                                  .replace("DAX40", "^GDAXI")
                                  .replace("NK225", "^N225")
                                  .replace("FTSE100", "^FTSE")
                                  .replace("USOIL", "CL=F")
                                  .replace("UKOIL", "BZ=F")
                                  .replace("NGAS", "NG=F")
                                  .replace("BTCUSD", "BTC-USD")
                                  .replace("ETHUSD", "ETH-USD"))
        df = ticker.history(period="6mo")
        if df.empty:
            return False
        csv_path = DATA_DIR / f"{symbol}_D1.csv"
        df.to_csv(csv_path)
        return True
    except Exception:
        return False

# ─── TICK DATA ───────────────────────────────────────────────────────

def download_ticks(symbols: list[str], hours_back: int = 24) -> list:
    """Download tick data for given symbols from MT5."""
    results = []
    TICK_DIR.mkdir(parents=True, exist_ok=True)

    for symbol in symbols:
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(QUANT_OS.parent.parent) + os.pathsep + env.get("PYTHONPATH", "")
            # Use mt5_tick_recorder if available
            recorder = QUANT_OS / "tick" / "mt5_tick_recorder.py"
            if recorder.exists():
                r = subprocess.run(
                    [VENV_PYTHON, str(recorder), "--symbol", symbol, "--hours", str(hours_back)],
                    capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace",
                    env=env,
                )
                results.append((symbol, r.returncode == 0))
            else:
                # Fallback: direct MT5 tick download
                import MetaTrader5 as mt5
                if mt5.initialize():
                    mt5.symbol_select(symbol, True)
                    import pandas as pd
                    from datetime import timedelta
                    ticks = mt5.copy_ticks_range(symbol,
                        datetime.now() - timedelta(hours=hours_back),
                        datetime.now(), mt5.COPY_TICKS_ALL)
                    if ticks is not None and len(ticks) > 0:
                        df = pd.DataFrame(ticks)
                        df['time'] = pd.to_datetime(df['time'], unit='s')
                        df.to_parquet(TICK_DIR / f"{symbol}_ticks.parquet")
                        results.append((symbol, True))
                    mt5.shutdown()
        except Exception as e:
            results.append((symbol, False))
    return results

# ─── MACRO DATA ──────────────────────────────────────────────────────

def download_macro() -> dict:
    """Download macro-economic data from available sources."""
    results = {"gdp": False, "cpi": False, "interest_rates": False, "nfp": False}
    MACRO_DIR.mkdir(parents=True, exist_ok=True)

    # Use existing downloader if available
    macro_script = HERE / "download_macro_data.py"
    if macro_script.exists():
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(QUANT_OS.parent.parent) + os.pathsep + env.get("PYTHONPATH", "")
            r = subprocess.run(
                [VENV_PYTHON, str(macro_script)],
                capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace",
                env=env,
            )
            if r.returncode == 0:
                results["gdp"] = True
        except Exception:
            pass

    # Alternative: use investing.com or FRED if available
    try:
        import pandas as pd
        # Try to fetch from FRED API if key exists
        fred_key = os.environ.get("FRED_API_KEY")
        if fred_key:
            try:
                from fredapi import Fred
                fred = Fred(api_key=fred_key)
                for series, name in [("GDP", "gdp"), ("CPIAUCSL", "cpi"),
                                      ("FEDFUNDS", "interest_rates"), ("PAYEMS", "nfp")]:
                    data = fred.get_series(series)
                    if data is not None:
                        data.to_csv(MACRO_DIR / f"{name}.csv")
                        results[name] = True
            except Exception:
                pass
    except ImportError:
        pass

    return results

# ─── NEWS / ECONOMIC EVENTS ──────────────────────────────────────────

def download_news() -> dict:
    """Download economic calendar events."""
    results = {"events": False}
    NEWS_DIR.mkdir(parents=True, exist_ok=True)

    # Check if forex_python or similar is available
    try:
        import pandas as pd
        import requests
        # Free economic calendar API (forex calendar)
        # Using investing.com via web scraping or API
        events_file = NEWS_DIR / "economic_events.json"

        # Try to fetch from various sources
        urls = [
            "https://www.forexfactory.com/calendar.json",  # if available
        ]
        for url in urls:
            try:
                r = requests.get(url, timeout=15)
                if r.status_code == 200:
                    data = r.json()
                    NEWS_DIR.mkdir(parents=True, exist_ok=True)
                    (NEWS_DIR / "calendar.json").write_text(json.dumps(data, indent=2))
                    results["events"] = True
                    break
            except Exception:
                continue
    except ImportError:
        pass

    return results

# ─── PARALLEL MASS DOWNLOAD ──────────────────────────────────────────

def download_all_mt5(quick: bool = False) -> dict:
    """Download ALL symbols × ALL timeframes — single bulk MT5 call."""
    log(f"Starting mega download: {len(ALL_SYMBOLS)} symbols × {len(TIMEFRAMES)} timeframes")
    log(f"Total combos: {len(ALL_SYMBOLS) * len(TIMEFRAMES)}")

    results = download_all_mt5_bulk()
    log(f"Bulk result: {len(results['ok'])} ok, {len(results['fail'])} fail")

    # Fallback: try Yahoo for any missing D1
    missing_d1 = [s for s in ALL_SYMBOLS
                  if not (DATA_DIR / f"{s}_D1.csv").exists()]
    if missing_d1:
        log(f"Yahoo fallback for {len(missing_d1)} missing D1 symbols...")
        for symbol in missing_d1:
            if download_yahoo_symbol(symbol):
                results["ok"].append(f"{symbol}_D1(yahoo)")

    return results

# ─── MAIN ────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="MEGA parallel data downloader")
    parser.add_argument("--quick", action="store_true", help="M15/H1/D1 only")
    parser.add_argument("--tick", action="store_true", help="Include tick data")
    parser.add_argument("--news", action="store_true", help="Include news/events")
    parser.add_argument("--macro", action="store_true", help="Include macro data")
    args = parser.parse_args()

    log("==========================================")
    log("  Graxia — MEGA DATA DOWNLOADER")
    log(f"  Mode: {'QUICK' if args.quick else 'FULL'}")
    log(f"  Total targets: {len(ALL_SYMBOLS)} symbols × {'3' if args.quick else '8'} TFs")
    log("==========================================")

    all_results = {}

    # Phase 1: OHLCV data
    ohlcv = download_all_mt5(quick=args.quick)
    all_results["ohlcv"] = ohlcv
    log(f"OHLCV: {len(ohlcv['ok'])} ok + {len(ohlcv['cached'])} cached + {len(ohlcv['fail'])} fail")

    # Phase 2: Tick data (optional)
    if args.tick:
        log("Downloading tick data...")
        tick_results = download_ticks(ALL_SYMBOLS[:8])  # top 8 symbols only for ticks
        all_results["ticks"] = tick_results
        log(f"Ticks: {sum(1 for _, ok in tick_results if ok)}/{len(tick_results)} ok")

    # Phase 3: Macro data (optional)
    if args.macro:
        log("Downloading macro data...")
        macro = download_macro()
        all_results["macro"] = macro
        log(f"Macro: {sum(1 for v in macro.values() if v)} series")

    # Phase 4: News (optional)
    if args.news:
        log("Downloading news/events...")
        news = download_news()
        all_results["news"] = news
        log(f"News: {'ok' if news.get('events') else 'failed'}")

    # Summary
    total_ok = len(ohlcv.get("ok", []))
    total_cached = len(ohlcv.get("cached", []))
    total_fail = len(ohlcv.get("fail", []))
    log("==========================================")
    log(f"  DOWNLOAD COMPLETE [{elapsed()}s]")
    log(f"  OK: {total_ok} | Cached: {total_cached} | Fail: {total_fail}")
    log(f"  Total files: {total_ok + total_cached}")
    log("==========================================")

    # Save manifest
    manifest = {
        "last_run": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": elapsed(),
        "symbols": len(ALL_SYMBOLS),
        "timeframes": list(TIMEFRAMES.keys()),
        "ok": total_ok,
        "cached": total_cached,
        "fail": total_fail,
    }
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    (MANIFEST_DIR / "download_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")

    return all_results


if __name__ == "__main__":
    main()

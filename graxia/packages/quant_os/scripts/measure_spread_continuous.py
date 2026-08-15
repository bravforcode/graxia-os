"""
Continuous Spread Measurement — 7+ Day Session-Separated Baseline
=================================================================
Records real MT5 spreads every 5 minutes for the tradeable universe
(XAUUSD, NAS100, USDJPY, OIL). Separates by session (Asian/London/NY).
Outputs summary statistics.

Each invocation connects fresh (explicit login via core.config.get_config(),
with reconnect-with-backoff on failure — same 3-attempt/2-4-8s pattern as
execution/adapters/mt5.py::MT5Adapter._ensure_connected), takes one snapshot,
appends it to today's day file, and disconnects. This makes --once safe to
run unattended every 5 minutes from Windows Task Scheduler: a crashed/missed
run just means one missing sample, not a wedged long-lived process.

Usage:
    python scripts/measure_spread_continuous.py --once
    python scripts/measure_spread_continuous.py --duration-days 7
    python scripts/measure_spread_continuous.py --duration-days 14 --symbols XAUUSD EURUSD

Output:
    data/spread_measurements/YYYY-MM-DD.json  (one file per day)
    data/spread_measurements/summary.json     (aggregated stats)

Note: the OIL leg trades on this MT5/Pepperstone-Demo account under the
broker symbol 'SpotCrude', NOT 'USOIL' (mt5.symbol_info('USOIL') returns
None; mt5.symbol_info('SpotCrude') resolves). config/cost_calibration.json
and config/tradeable_universe.json still key OIL by the literal 'USOIL'
string (because scripts/tsm_paper_trade.py's MT5_SYMBOL_MAP hardcodes that
key) — this script polls the real resolvable symbol 'SpotCrude' and records
both `mt5_symbol` ("SpotCrude") and `display_symbol` ("OIL") per measurement
so a future cost_calibration.json update can join on either.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "spread_measurements"

# Tradeable-universe default (matches config/cost_calibration.json's
# "4-asset focused portfolio"). OIL is polled under its real MT5 symbol.
DEFAULT_SYMBOLS = ["XAUUSD", "NAS100", "USDJPY", "SpotCrude"]

# Real MT5 broker symbol -> display/canonical name used elsewhere in the repo.
SYMBOL_DISPLAY_MAP = {"SpotCrude": "OIL"}

# This script never places orders — it only reads ticks/spreads. Some
# environments have a stray User/Machine-level TRADING_MODE env var (e.g.
# "DEMO") that core.config.QuantConfig rejects (fail-closed, valid values
# are PAPER/LIVE_MICRO/LIVE_LIMITED/LIVE_CONTROLLED). Force a valid value
# for THIS PROCESS ONLY (does not touch the persistent Windows env var) so
# get_config() can load MT5 credentials without crashing.
os.environ.setdefault("_TRADING_MODE_ORIGINAL", os.environ.get("TRADING_MODE", ""))
if os.environ.get("TRADING_MODE", "").upper() not in {
    "PAPER",
    "LIVE_MICRO",
    "LIVE_LIMITED",
    "LIVE_CONTROLLED",
}:
    os.environ["TRADING_MODE"] = "paper"


def _get_mt5_credentials() -> dict | None:
    """Load MT5 credentials via graxia.packages.quant_os.core.config.get_config().

    Returns None (falls back to anonymous mt5.initialize()) if the config
    module can't be imported from this invocation context — never raises.
    """
    try:
        graxia_root = ROOT.parent.parent.parent  # .../graxia os (parent of the 'graxia' package dir)
        if str(graxia_root) not in sys.path:
            sys.path.insert(0, str(graxia_root))
        from graxia.packages.quant_os.core.config import get_config

        cfg = get_config()
        return {
            "login": cfg.mt5_login,
            "password": cfg.mt5_password,
            "server": cfg.mt5_server,
            "path": cfg.mt5_path,
            "timeout": cfg.mt5_timeout_ms,
        }
    except Exception as e:
        print(
            f"  WARNING: could not load MT5 credentials via get_config() ({e}); "
            f"falling back to anonymous mt5.initialize()"
        )
        return None


def _connect_mt5_with_backoff(mt5_module, max_attempts: int = 3) -> bool:
    """Connect + authenticate to MT5, retrying with backoff (2s, 4s, 8s).

    Mirrors execution/adapters/mt5.py::MT5Adapter._ensure_connected().
    """
    creds = _get_mt5_credentials()

    for attempt in range(1, max_attempts + 1):
        try:
            if creds is not None:
                ok = mt5_module.initialize(path=creds["path"], timeout=creds["timeout"])
                if ok:
                    ok = mt5_module.login(creds["login"], password=creds["password"], server=creds["server"])
            else:
                ok = mt5_module.initialize()

            if ok:
                return True
            print(f"  MT5 connect attempt {attempt}/{max_attempts} failed: " f"{mt5_module.last_error()}")
        except Exception as e:
            print(f"  MT5 connect attempt {attempt}/{max_attempts} raised: {e}")

        if attempt < max_attempts:
            time.sleep(min(2**attempt, 10))

    return False


# Session boundaries (UTC hours)
SESSIONS = {
    "asian": (0, 7),
    "london": (7, 12),
    "ny": (12, 21),
    "off_hours": (21, 24),  # After NY close
}


def get_session(hour_utc: int) -> str:
    """Classify UTC hour into trading session."""
    for name, (start, end) in SESSIONS.items():
        if start <= hour_utc < end:
            return name
    return "asian"


def measure_once(symbols: list[str]) -> list[dict]:
    """Take one measurement snapshot for all symbols."""
    try:
        import MetaTrader5 as mt5  # noqa: N813 — canonical MT5 alias used across the repo
    except ImportError:
        print("ERROR: MetaTrader5 not installed. Run: pip install MetaTrader5")
        sys.exit(1)

    if not _connect_mt5_with_backoff(mt5):
        print(f"ERROR: MT5 connect failed after retries: {mt5.last_error()}")
        return []

    now = datetime.now(UTC)
    measurements = []

    for sym_name in symbols:
        try:
            # Make sure the symbol is subscribed so ticks actually flow.
            info_check = mt5.symbol_info(sym_name)
            if info_check is not None and not info_check.visible:
                mt5.symbol_select(sym_name, True)

            tick = mt5.symbol_info_tick(sym_name)
            sym_info = mt5.symbol_info(sym_name)
            if tick is None or sym_info is None:
                print(f"  WARNING: {sym_name} not found/no tick on this account")
                continue

            bid = tick.bid
            ask = tick.ask
            if bid <= 0 or ask <= 0:
                continue

            spread_points = ask - bid
            mid = (ask + bid) / 2.0
            spread_bps = (spread_points / mid) * 10000 if mid > 0 else 0

            measurements.append(
                {
                    "symbol": sym_name,
                    "display_symbol": SYMBOL_DISPLAY_MAP.get(sym_name, sym_name),
                    "mt5_symbol": sym_name,
                    "timestamp_utc": now.isoformat(),
                    "bid": bid,
                    "ask": ask,
                    "spread_points": round(spread_points, 6),
                    "spread_bps": round(spread_bps, 4),
                    "session": get_session(now.hour),
                    "point": sym_info.point,
                    "digits": sym_info.digits,
                }
            )
        except Exception as e:
            print(f"  WARNING: {sym_name} measurement failed: {e}")
            continue

    mt5.shutdown()
    return measurements


def save_day(day_data: list[dict], date_str: str, output_suffix: str = "") -> Path:
    """Save measurements for one day as JSON.

    With ``output_suffix`` set (e.g. ``directionG``), writes to
    ``<date_str>_<output_suffix>.json`` instead of ``<date_str>.json`` so a
    focused sampling run never collides with the default daily daemon file.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"{date_str}.json" if not output_suffix else f"{date_str}_{output_suffix}.json"
    path = DATA_DIR / fname

    # Merge with existing if file exists
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        existing.extend(day_data)
        day_data = existing

    path.write_text(json.dumps(day_data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def compute_summary(all_measurements: list[dict]) -> dict:
    """Compute per-symbol, per-session summary statistics."""
    import statistics
    from collections import defaultdict

    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for m in all_measurements:
        grp_key = (m["symbol"], m["session"])
        grouped[grp_key].append(m["spread_bps"])

    summary = {}
    for (symbol, session), values in sorted(grouped.items()):
        if not values:
            continue
        values_sorted = sorted(values)
        n = len(values_sorted)
        stat_key = f"{symbol}_{session}"
        summary[stat_key] = {
            "symbol": symbol,
            "session": session,
            "n_samples": n,
            "min_bps": round(values_sorted[0], 4),
            "max_bps": round(values_sorted[-1], 4),
            "mean_bps": round(statistics.mean(values), 4),
            "median_bps": round(statistics.median(values), 4),
            "p95_bps": round(values_sorted[int(n * 0.95)] if n >= 20 else values_sorted[-1], 4),
            "std_bps": round(statistics.stdev(values), 4) if n >= 2 else 0,
        }

    # Also compute overall per-symbol summary
    symbol_overall: dict[str, list[float]] = defaultdict(list)
    for m in all_measurements:
        symbol_overall[m["symbol"]].append(m["spread_bps"])

    for symbol, values in sorted(symbol_overall.items()):
        if not values:
            continue
        values_sorted = sorted(values)
        n = len(values_sorted)
        stat_key = f"{symbol}_ALL"
        summary[stat_key] = {
            "symbol": symbol,
            "session": "ALL",
            "n_samples": n,
            "min_bps": round(values_sorted[0], 4),
            "max_bps": round(values_sorted[-1], 4),
            "mean_bps": round(statistics.mean(values), 4),
            "median_bps": round(statistics.median(values), 4),
            "p95_bps": round(values_sorted[int(n * 0.95)] if n >= 20 else values_sorted[-1], 4),
            "std_bps": round(statistics.stdev(values), 4) if n >= 2 else 0,
        }

    return summary


def run_measurement(duration_days: int, symbols: list[str], interval_sec: int = 300, output_suffix: str = ""):
    """Main measurement loop."""
    print("=== Continuous Spread Measurement ===")
    print(f"Duration: {duration_days} days")
    print(f"Interval: {interval_sec}s (every {interval_sec // 60} min)")
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Output: {DATA_DIR}")
    if output_suffix:
        print(f"Output suffix: _{output_suffix} (separate from daily daemon files)")
    print()

    end_time = datetime.now(UTC) + timedelta(days=duration_days)
    all_measurements = []
    day_buckets: dict[str, list[dict]] = {}

    sample_count = 0
    while datetime.now(UTC) < end_time:
        now = datetime.now(UTC)
        date_str = now.strftime("%Y-%m-%d")

        measurements = measure_once(symbols)
        if measurements:
            all_measurements.extend(measurements)

            # Bucket by day
            if date_str not in day_buckets:
                day_buckets[date_str] = []
            day_buckets[date_str].extend(measurements)

            sample_count += 1
            if sample_count % 12 == 0:  # Every hour (12 x 5min)
                print(
                    f"  [{now.strftime('%Y-%m-%d %H:%M UTC')}] "
                    f"Samples: {sample_count}, "
                    f"Total measurements: {len(all_measurements)}"
                )

            # Save daily file at end of day or every 100 measurements
            if len(day_buckets[date_str]) >= 100 or now.hour == 23:
                save_day(day_buckets[date_str], date_str, output_suffix)
                day_buckets[date_str] = []

        # Sleep until next interval
        time.sleep(interval_sec)

    # Final save for any remaining data
    for date_str, data in day_buckets.items():
        if data:
            save_day(data, date_str, output_suffix)

    # Generate summary
    if all_measurements:
        summary = compute_summary(all_measurements)
        summary_path = DATA_DIR / "summary.json"
        summary_path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print("\n=== Measurement Complete ===")
        print(f"Total measurements: {len(all_measurements)}")
        print(f"Summary saved to: {summary_path}")

        # Print quick summary
        print(f"\n{'Symbol':<10} {'Session':<12} {'N':>5} {'Mean':>8} {'P95':>8} {'Max':>8}")
        print("-" * 60)
        for key, stats in sorted(summary.items()):
            if stats["session"] != "ALL":
                print(
                    f"{stats['symbol']:<10} {stats['session']:<12} "
                    f"{stats['n_samples']:>5} {stats['mean_bps']:>8.2f} "
                    f"{stats['p95_bps']:>8.2f} {stats['max_bps']:>8.2f}"
                )
    else:
        print("\nERROR: No measurements collected. Check MT5 connection.")


def main():
    parser = argparse.ArgumentParser(description="Continuous spread measurement for cost calibration")
    parser.add_argument("--duration-days", type=int, default=7, help="Measurement duration in days (default: 7)")
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS, help="Symbols to measure")
    parser.add_argument("--interval", type=int, default=300, help="Measurement interval in seconds (default: 300)")
    parser.add_argument("--once", action="store_true", help="Take single snapshot and exit (no loop)")
    parser.add_argument(
        "--output-suffix",
        type=str,
        default="",
        help="Suffix for output filenames (e.g. 'directionG' -> YYYY-MM-DD_directionG.json). "
        "Use when running alongside the default daily daemon to avoid colliding with "
        "its YYYY-MM-DD.json files.",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="With --once: print the snapshot instead of appending it to data/spread_measurements/<date>.json "
        "(default for --once is to persist, so it's safe to schedule as a recurring task)",
    )
    args = parser.parse_args()

    if args.once:
        measurements = measure_once(args.symbols)
        if not measurements:
            print("No measurements collected.")
            return
        if args.no_save:
            print(json.dumps(measurements, indent=2))
            return
        date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        path = save_day(measurements, date_str, args.output_suffix)
        print(f"Saved {len(measurements)} measurements -> {path}")
        return

    run_measurement(args.duration_days, args.symbols, args.interval, args.output_suffix)


if __name__ == "__main__":
    main()

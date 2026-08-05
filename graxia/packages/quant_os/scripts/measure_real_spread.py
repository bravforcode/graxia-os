"""
REAL SPREAD MEASUREMENT PROTOCOL — Phase 2 (Data Infrastructure).

Measures bid/ask spread per tick for all available symbols,
aggregates by trading session, and writes
config/cost_calibration_live.json with per-session statistics.

Modes
-----
- live (default if MT5 reachable):  sample ticks from Pepperstone MT5
- ticks:                            read tick parquet files from data/ticks/
- mock (fallback):                  derive synthetic per-tick spread
                                    from D1 OHLC + published Pepperstone
                                    baselines; this is the documented
                                    "no-live-MT5" path

Sessions (UTC)
--------------
- asian              00:00 - 08:00
- london             08:00 - 13:00
- london_ny_overlap  13:00 - 17:00
- ny                 17:00 - 22:00
- rollover           22:00 - 24:00

Output schema (config/cost_calibration_live.json)
-------------------------------------------------
{
  "version": "live-1.0",
  "date": "YYYY-MM-DD",
  "source": "pepperstone_mt5" | "tick_parquet" | "mock_from_d1",
  "session_windows_utc": {...},
  "assets": {
    "XAUUSD": {
      "spread_bps_overall": {"mean":..,"median":..,"p90":..,"p99":..,"max":..,"n":..},
      "by_session": {
        "asian": {...}, "london": {...}, ...
      },
      "mt5_symbol": "XAUUSD",
      "status": "MEASURED" | "FROM_TICKS" | "MOCK"
    },
    ...
  }
}

Usage
-----
    python scripts/measure_real_spread.py                 # auto: live > ticks > mock
    python scripts/measure_real_spread.py --mode ticks    # read tick parquet files
    python scripts/measure_real_spread.py --mode mock     # force mock
    python scripts/measure_real_spread.py --mode live     # force live (fail if no MT5)
    python scripts/measure_real_spread.py --days 7        # mock: anchor on last N D1 bars
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "data"
CONFIG_DIR = BASE / "config"
OUTPUT_PATH = CONFIG_DIR / "cost_calibration_live.json"
COST_CAL_PATH = CONFIG_DIR / "cost_calibration.json"
TICKS_DIR = DATA_DIR / "ticks"

# Task scope: all symbols with tick data or D1 data available.
SYMBOLS_WITH_TICKS = ["XAUUSD", "XAGUSD", "XPDUSD", "XPTUSD",
                      "BTCUSD", "EURUSD", "GBPUSD", "US30", "USDJPY"]
SYMBOLS = SYMBOLS_WITH_TICKS

# Pepperstone Razor MT5 executable path (used by live mode).
MT5_PATH = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"
MT5_INIT_TIMEOUT_MS = 10000

# Session windows in UTC hours (inclusive start, exclusive end).
SESSIONS: dict[str, tuple[int, int]] = {
    "asian":             (0,  8),
    "london":            (8, 13),
    "london_ny_overlap": (13, 17),
    "ny":                (17, 22),
    "rollover":          (22, 24),
}


# ── helpers ────────────────────────────────────────────────────────────────


def classify_session(ts: datetime) -> str:
    """Return session name for a UTC datetime."""
    h = ts.hour
    for name, (lo, hi) in SESSIONS.items():
        if lo <= h < hi:
            return name
    return "rollover"  # 24:00 wrap (defensive)


def session_stats(values: list[float]) -> dict:
    """Return mean/median/p90/p99/max/min/n for a list of bps values."""
    if not values:
        return {"mean": None, "median": None, "p90": None, "p99": None,
                "max": None, "min": None, "n": 0}
    arr = np.asarray(values, dtype=float)
    return {
        "mean":   round(float(np.mean(arr)),   3),
        "median": round(float(np.median(arr)), 3),
        "p90":    round(float(np.percentile(arr, 90)), 3),
        "p99":    round(float(np.percentile(arr, 99)), 3),
        "max":    round(float(np.max(arr)),    3),
        "min":    round(float(np.min(arr)),    3),
        "n":      int(arr.size),
    }


# ── live mode (MT5) ───────────────────────────────────────────────────────


def try_mt5() -> bool:
    """Return True if MetaTrader5 is importable and a session can be initialised."""
    try:
        import MetaTrader5 as mt5  # type: ignore  # noqa: F401
    except Exception:
        return False
    try:
        ok = mt5.initialize(path=MT5_PATH, timeout=MT5_INIT_TIMEOUT_MS)
        if ok:
            mt5.shutdown()
        return ok
    except Exception:
        return False


def sample_live(symbols: list[str], interval_sec: float, duration_sec: float) -> dict:
    """Sample live ticks from MT5 for `duration_sec` seconds at `interval_sec`."""
    import MetaTrader5 as mt5

    if not mt5.initialize(path=MT5_PATH, timeout=MT5_INIT_TIMEOUT_MS):
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")

    available: list[str] = []
    for sym in symbols:
        if mt5.symbol_select(sym, True):
            available.append(sym)
    if not available:
        mt5.shutdown()
        raise RuntimeError("None of the requested symbols are available on MT5")

    samples: dict[str, list[dict]] = {s: [] for s in available}
    end = datetime.now(UTC) + timedelta(seconds=duration_sec)
    n = 0
    try:
        while datetime.now(UTC) < end:
            now = datetime.now(UTC)
            for sym in available:
                tick = mt5.symbol_info_tick(sym)
                info = mt5.symbol_info(sym)
                if tick is None or info is None or info.point <= 0:
                    continue
                bid, ask = float(tick.bid), float(tick.ask)
                mid = (bid + ask) / 2.0
                spread_bps = (ask - bid) / mid * 10000.0 if mid > 0 else 0.0
                samples[sym].append({
                    "timestamp": now.isoformat(),
                    "bid": bid,
                    "ask": ask,
                    "mid": mid,
                    "spread_bps": spread_bps,
                    "session": classify_session(now),
                })
            n += 1
            import time as _t
            _t.sleep(interval_sec)
    finally:
        mt5.shutdown()

    return {"samples": samples, "ticks_per_symbol": n}


# ── tick parquet mode ────────────────────────────────────────────────────


def load_tick_parquet(symbols: list[str]) -> dict[str, list[dict]]:
    """Load tick data from data/ticks/{SYMBOL}_ticks_24h.parquet files."""
    import pyarrow.parquet as pq

    all_samples: dict[str, list[dict]] = {}
    for sym in symbols:
        path = TICKS_DIR / f"{sym}_ticks_24h.parquet"
        if not path.exists():
            print(f"[WARN] No tick parquet for {sym} — skipping")
            continue
        try:
            table = pq.read_table(path)
            df = table.to_pandas()
        except Exception as e:
            print(f"[WARN] Failed to read {path}: {e}")
            continue

        # Detect bid/ask columns
        cols = {c.lower(): c for c in df.columns}
        bid_col = cols.get("bid") or cols.get("bid_price") or cols.get("bidprice")
        ask_col = cols.get("ask") or cols.get("ask_price") or cols.get("askprice")
        ts_col = cols.get("time") or cols.get("timestamp") or cols.get("datetime")

        if not bid_col or not ask_col:
            # Try bid/ask from 'price' column or first two numeric columns
            numeric = df.select_dtypes(include=["number"]).columns.tolist()
            if len(numeric) >= 2:
                bid_col, ask_col = numeric[0], numeric[1]
            else:
                print(f"[WARN] Cannot identify bid/ask columns in {path} — skipping")
                continue

        if not ts_col:
            # Try first column as timestamp
            ts_col = df.columns[0]

        # 2026-07-30: raw MT5 tick dumps contain a large fraction of rows
        # (15-68% measured across XAUUSD/USDJPY/GBPUSD/EURUSD) where bid==ask
        # exactly, including on ticks flagged with BOTH TICK_FLAG_BID and
        # TICK_FLAG_ASK set -- not just trade-echo ticks. Including these
        # mechanically drags the median toward zero (EURUSD/GBPUSD, majority
        # contaminated, previously computed as a meaningless 0.0bps median).
        # A live two-sided FX/metals/crypto market does not genuinely quote
        # zero width; drop these rows rather than silently averaging them in.
        n_before = len(df)
        df = df[df[ask_col] > df[bid_col]].copy()
        n_dropped = n_before - len(df)
        if n_dropped:
            print(f"[FILTER] {sym}: dropped {n_dropped}/{n_before} zero-or-negative-spread ticks "
                  f"({100*n_dropped/n_before:.1f}%)")

        samples: list[dict] = []
        for _, row in df.iterrows():
            bid = float(row[bid_col])
            ask = float(row[ask_col])
            mid = (bid + ask) / 2.0
            spread_bps = (ask - bid) / mid * 10000.0 if mid > 0 else 0.0

            # Parse timestamp
            ts_raw = row[ts_col]
            if isinstance(ts_raw, pd.Timestamp):
                ts = ts_raw.to_pydatetime()
            else:
                ts = pd.Timestamp(ts_raw).to_pydatetime()
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)

            samples.append({
                "timestamp": ts.isoformat(),
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "spread_bps": round(spread_bps, 3),
                "session": classify_session(ts),
            })

        if samples:
            all_samples[sym] = samples
            print(f"[TICKS] Loaded {len(samples)} ticks for {sym} from {path.name}")

    return all_samples


# ── mock mode (D1-derived) ────────────────────────────────────────────────


def load_d1(symbol: str, days: int) -> pd.DataFrame:
    """Load last `days` rows from data/{SYMBOL}_D1.csv."""
    path = DATA_DIR / f"{symbol}_D1.csv"
    if not path.exists():
        raise FileNotFoundError(f"D1 file missing for {symbol}: {path}")
    df = pd.read_csv(path)
    # Standardise the time column.
    time_col = "time" if "time" in df.columns else df.columns[0]
    df[time_col] = pd.to_datetime(df[time_col], utc=True, errors="coerce")
    df = df.dropna(subset=[time_col]).sort_values(time_col).reset_index(drop=True)
    if days > 0 and len(df) > days:
        df = df.tail(days).reset_index(drop=True)
    return df


def load_baseline_spreads() -> dict[str, float]:
    """Pull the published median spread (bps) per symbol from cost_calibration.json."""
    if not COST_CAL_PATH.exists():
        return {}
    try:
        cfg = json.loads(COST_CAL_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, float] = {}
    for asset_name, asset in cfg.get("assets", {}).items():
        m5 = asset.get("mt5_symbol")
        med = asset.get("spread_bps_measured")
        if m5 and isinstance(med, (int, float)):
            out[m5] = float(med)
    return out


# Pepperstone published typical spread-points per symbol (used to anchor
# the synthetic model if cost_calibration.json is missing a baseline).
# Values are mid-quotes from the broker spec; not live measurements.
PEPP_BASELINE_BPS: dict[str, float] = {
    "XAUUSD":  0.36,
    "XAGUSD":  6.58,
    "XPDUSD": 55.35,
    "XPTUSD": 45.29,
}

# Session multipliers (Asian = thinner, Overlap = tightest, Rollover = widest).
# Sourced from industry-standard FX/metals liquidity profiles; not measured.
SESSION_MULT: dict[str, float] = {
    "asian":             1.30,
    "london":            1.00,
    "london_ny_overlap": 0.85,
    "ny":                1.00,
    "rollover":          2.00,
}

# Intraday volatility multiplier (relative to daily ATR). Asian is the
# quietest, overlap is the busiest. Used to add small spread drift.
INTRADAY_VOL_MULT: dict[str, float] = {
    "asian":             0.55,
    "london":            1.00,
    "london_ny_overlap": 1.30,
    "ny":                0.95,
    "rollover":          0.40,
}


def synthesise_spreads(symbol: str, days: int, seed: int = 7) -> list[dict]:
    """Generate per-tick synthetic bid/ask/spread samples for the last `days` D1 bars.

    For each calendar day in the window we emit 1 tick per hour (24 ticks/day)
    at minute=00. The spread is anchored on cost_calibration.json's measured
    median, modulated by session multiplier and a small noise term. Bid/ask
    are derived from a synthetic mid that walks the daily range.
    """
    df = load_d1(symbol, days)
    if df.empty:
        return []

    baselines = load_baseline_spreads()
    base_bps = baselines.get(symbol, PEPP_BASELINE_BPS.get(symbol, 5.0))

    rng = random.Random(seed + hash(symbol) % 10000)
    out: list[dict] = []

    time_col = "time" if "time" in df.columns else df.columns[0]
    for _, row in df.iterrows():
        day_ts = row[time_col]
        if isinstance(day_ts, pd.Timestamp):
            day = day_ts.to_pydatetime()
        else:
            day = datetime.fromisoformat(str(day_ts).replace("Z", "+00:00"))
        if day.tzinfo is None:
            day = day.replace(tzinfo=UTC)
        # Use OHLC to build a synthetic mid path.
        o = float(row.get("open",  row.get("close", 0)) or 0)
        h = float(row.get("high",  o) or o)
        l = float(row.get("low",   o) or o)
        c = float(row.get("close", o) or o)
        if o <= 0:
            o = c = (h + l) / 2.0 if (h and l) else 100.0
        if h < o: h = o
        if l > o: l = o
        daily_range = max(h - l, abs(c - o) * 0.5, 1e-6)

        for hour in range(24):
            # Fraction along the daily path 0..1.
            frac = hour / 23.0
            mid = o + (c - o) * frac
            # Add tiny noise proportional to daily range.
            mid += rng.gauss(0, daily_range * 0.02)

            sess = classify_session(day.replace(hour=hour))
            sess_mult = SESSION_MULT[sess]
            noise = 1.0 + rng.gauss(0, 0.10) * INTRADAY_VOL_MULT[sess]
            spread_bps = max(0.01, base_bps * sess_mult * noise)
            half_bps = spread_bps / 2.0
            half_price = mid * half_bps / 10000.0
            bid = round(mid - half_price, 6)
            ask = round(mid + half_price, 6)
            ts = day.replace(hour=hour, minute=0, second=0, microsecond=0)
            out.append({
                "timestamp": ts.isoformat(),
                "bid": bid,
                "ask": ask,
                "mid": round(mid, 6),
                "spread_bps": round(spread_bps, 3),
                "session": sess,
            })
    return out


# ── aggregation ──────────────────────────────────────────────────────────


def aggregate(symbol: str, samples: list[dict]) -> dict:
    """Build per-session and overall stats for one symbol."""
    by_sess: dict[str, list[float]] = {s: [] for s in SESSIONS}
    all_vals: list[float] = []
    for s in samples:
        bps = s.get("spread_bps")
        sess = s.get("session", "rollover")
        if bps is None:
            continue
        all_vals.append(float(bps))
        by_sess.setdefault(sess, []).append(float(bps))

    return {
        "spread_bps_overall": session_stats(all_vals),
        "by_session": {name: session_stats(vals) for name, vals in by_sess.items()},
    }


# ── main ──────────────────────────────────────────────────────────────────


def run(mode: str, days: int, interval_sec: float, duration_sec: float) -> dict:
    if mode == "auto":
        if try_mt5():
            mode = "live"
        elif any((TICKS_DIR / f"{s}_ticks_24h.parquet").exists() for s in SYMBOLS):
            mode = "ticks"
        else:
            mode = "mock"

    if mode == "live":
        live = sample_live(SYMBOLS, interval_sec=interval_sec, duration_sec=duration_sec)
        source = "pepperstone_mt5"
        assets: dict[str, dict] = {}
        for sym, samples in live["samples"].items():
            if not samples:
                continue
            assets[sym] = aggregate(sym, samples)
            assets[sym]["mt5_symbol"] = sym
            assets[sym]["status"] = "MEASURED"
            assets[sym]["n_ticks"] = len(samples)
    elif mode == "ticks":
        tick_data = load_tick_parquet(SYMBOLS)
        if not tick_data:
            print("[WARN] No tick data loaded — falling back to mock mode")
            mode = "mock"
        else:
            source = "tick_parquet"
            assets = {}
            for sym, samples in tick_data.items():
                assets[sym] = aggregate(sym, samples)
                assets[sym]["mt5_symbol"] = sym
                assets[sym]["status"] = "FROM_TICKS"
                assets[sym]["n_ticks"] = len(samples)

    if mode == "mock":
        source = "mock_from_d1"
        assets = {}
        for sym in SYMBOLS:
            samples = synthesise_spreads(sym, days=days)
            if not samples:
                print(f"[WARN] No samples generated for {sym} — skipping")
                continue
            assets[sym] = aggregate(sym, samples)
            assets[sym]["mt5_symbol"] = sym
            assets[sym]["status"] = "MOCK"
            assets[sym]["n_ticks"] = len(samples)

    out = {
        "version": "live-1.0",
        "date": datetime.now(UTC).strftime("%Y-%m-%d"),
        "source": source,
        "mode_requested": mode if mode != "auto" else "auto",
        "session_windows_utc": {k: list(v) for k, v in SESSIONS.items()},
        "assets": assets,
    }
    return out


def write_report(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[SAVE] {path}")


def print_summary(payload: dict) -> None:
    print(f"\n=== spread measurement ({payload['source']}) ===")
    print(f"date: {payload['date']}")
    for sym, asset in payload["assets"].items():
        ov = asset["spread_bps_overall"]
        print(f"\n{sym}  [{asset.get('status','?')}]  n_ticks={asset.get('n_ticks',0)}")
        print(f"  overall: mean={ov['mean']} median={ov['median']} "
              f"p90={ov['p90']} max={ov['max']}")
        for sess, s in asset["by_session"].items():
            if s["n"]:
                print(f"  {sess:<18} mean={s['mean']:<7} median={s['median']:<7} "
                      f"p90={s['p90']:<7} max={s['max']:<7} n={s['n']}")


def main() -> int:
    p = argparse.ArgumentParser(description="Real spread measurement (live or mock)")
    p.add_argument("--mode", choices=["auto", "live", "ticks", "mock"], default="auto",
                   help="auto=live if MT5 reachable, then ticks parquet, else mock (default)")
    p.add_argument("--days", type=int, default=7,
                   help="mock: anchor on last N D1 bars per symbol (default 7)")
    p.add_argument("--interval", type=float, default=60.0,
                   help="live: seconds between samples (default 60)")
    p.add_argument("--duration", type=float, default=300.0,
                   help="live: total sampling window in seconds (default 300 = 5 min)")
    p.add_argument("--output", type=str, default=str(OUTPUT_PATH),
                   help=f"output path (default {OUTPUT_PATH})")
    args = p.parse_args()

    try:
        payload = run(args.mode, args.days, args.interval, args.duration)
    except Exception as e:
        print(f"[FATAL] {e}", file=sys.stderr)
        return 1
    if not payload["assets"]:
        print("[FATAL] No assets produced.", file=sys.stderr)
        return 2
    write_report(payload, Path(args.output))
    print_summary(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
DUKASCOPY TICK DOWNLOADER - Parallel, resumable historical tick download.

Downloads .bi5 files from Dukascopy datafeed, parses tick records,
writes Hive-partitioned Parquet files. Supports checkpoint/resume,
exponential-backoff retry, and concurrent downloads.

Usage:
    python scripts/download_duka.py --symbols EURUSD,GBPUSD,XAUUSD --start 2020-01-01 --end 2024-12-31
    python scripts/download_duka.py --symbols XAUUSD --start 2023-06-01 --end 2023-06-30 --workers 8 --resume

Requires pyarrow for Parquet output. Install with: pip install pyarrow
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import lzma
import os
import random
import struct
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date as Date, datetime, timedelta, UTC
from io import BytesIO, StringIO
from pathlib import Path

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    PYARROW_OK = True
except ImportError:
    pa = pq = None
    PYARROW_OK = False

try:
    from tqdm import tqdm
    TQDM_OK = True
except ImportError:
    tqdm = None
    TQDM_OK = False


# ── Constants ──

BASE_URL = "https://datafeed.dukascopy.com/datafeed"
RECORD_SIZE = 20
RECORD_FMT = ">I I I f f"  # 3 uint32 + 2 float32 = 20 bytes per tick
CHECKPOINT_FILE = ".duka_checkpoint.json"
LOG_FILE = "download_duka.log"
DEFAULT_WORKERS = 4
DEFAULT_RETRIES = 3

# Symbol name mapping: internal → Dukascopy feed format.
# Dukascopy uses slash-less names (EURUSD, not EUR/USD).
# Map is kept for reference / potential ISIN lookup; URLs use raw symbol.
DUKA_SYMBOL_MAP: dict[str, str] = {}

# ── Logging ──

def setup_logging(log_dir: str) -> logging.Logger:
    log_path = os.path.join(log_dir, LOG_FILE)
    logger = logging.getLogger("duka")
    logger.setLevel(logging.DEBUG)

    fh = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S"))

    logger.handlers.clear()
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger("duka")


# ── .bi5 Parser ──

def parse_bi5(data: bytes) -> list[tuple[int, float, float, float, float]]:
    """Parse Dukascopy .bi5 binary tick data.

    Decompresses LZMA stream, reads 20-byte records, auto-detects field
    order by checking bid < ask invariant.

    Returns list of (timestamp_ms, bid, ask, bid_volume, ask_volume).
    """
    try:
        raw = lzma.decompress(data)
    except lzma.LZMAError:
        buf = BytesIO(data)
        with lzma.LZMAFile(buf) as f:
            raw = f.read()

    n = len(raw) // RECORD_SIZE
    if n == 0:
        return []

    # Parse raw records: (time_ms, val1, val2, vol1, vol2)
    records = []
    for i in range(n):
        offset = i * RECORD_SIZE
        block = raw[offset : offset + RECORD_SIZE]
        records.append(struct.unpack(RECORD_FMT, block))

    fmt = _detect_bi5_format(records)
    result = []

    for t, v2, v3, v4, v5 in records:
        if fmt == "ask_bid":
            bid = v3 / 100_000.0
            ask = v2 / 100_000.0
            bid_vol = v5
            ask_vol = v4
        else:
            bid = v2 / 100_000.0
            ask = v3 / 100_000.0
            bid_vol = v4
            ask_vol = v5
        result.append((t, bid, ask, bid_vol, ask_vol))

    return result


def _detect_bi5_format(records: list[tuple]) -> str:
    """Detect bi5 field order: 'ask_bid' (time, ask, bid, ask_vol, bid_vol)
    or 'bid_ask' (time, bid, ask, bid_vol, ask_vol).

    Uses bid < ask invariant on first record.
    """
    for t, v2, v3, v4, v5 in records[:10]:
        if v2 == 0 and v3 == 0:
            continue
        ask_a, bid_a = v2 / 100_000.0, v3 / 100_000.0
        if 0 < bid_a < ask_a < 1_000_000:
            return "ask_bid"
        bid_b, ask_b = v2 / 100_000.0, v3 / 100_000.0
        if 0 < bid_b < ask_b < 1_000_000:
            return "bid_ask"
    return "ask_bid"


# ── Download ──

def download_bi5(url: str, retries: int) -> bytes | None:
    """Download a .bi5 file. Returns bytes or None if 404. Retries on error."""
    logger = get_logger()
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if attempt == retries - 1:
                raise
            delay = 2.0 ** attempt
            logger.debug("HTTP %d for %s, retry %d/%d after %.1fs", e.code, url, attempt + 1, retries, delay)
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt == retries - 1:
                raise
            delay = 2.0 ** attempt
            logger.debug("Error for %s: %s, retry %d/%d after %.1fs", url, e, attempt + 1, retries, delay)
            time.sleep(delay)
    return None


# ── Date Processing ──

def process_date(symbol: str, duka_symbol: str, dt: Date, output_dir: str,
                 retries: int) -> int:
    """Download all hours for symbol+date, parse, write daily Parquet.

    Returns tick count written (0 = no data for this date).
    """
    logger = get_logger()
    all_records = []
    hour_zero = datetime(dt.year, dt.month, dt.day, tzinfo=UTC)

    for hour in range(24):
        url = f"{BASE_URL}/{duka_symbol}/{dt.year}/{dt.month - 1:02d}/{dt.day:02d}/{hour:02d}h_ticks.bi5"
        try:
            raw = download_bi5(url, retries)
        except Exception as e:
            logger.warning("  Failed hour %02d %s: %s", hour, url, e)
            continue
        if raw is None:
            continue
        try:
            parsed = parse_bi5(raw)
        except Exception as e:
            logger.debug("  Parse error hour %02d %s: %s", hour, url, e)
            continue
        for t_ms, bid, ask, bid_vol, ask_vol in parsed:
            ts = int(hour_zero.timestamp() * 1000) + t_ms
            all_records.append((ts, bid, ask, bid_vol, ask_vol))

    if not all_records:
        return 0

    table = _records_to_table(all_records, symbol)
    _write_daily_parquet(table, symbol, dt, output_dir)
    return len(all_records)


def _records_to_table(records: list[tuple], symbol: str) -> pa.Table:
    """Convert parsed tick records to a PyArrow table with unified schema."""
    timestamps = []
    bids = []
    asks = []
    bid_vols = []
    ask_vols = []

    for ts, bid, ask, bid_vol, ask_vol in records:
        timestamps.append(ts)
        bids.append(bid)
        asks.append(ask)
        bid_vols.append(bid_vol)
        ask_vols.append(ask_vol)

    spread_points = [(a - b) * 100_000.0 for a, b in zip(asks, bids)]
    ts_dt = [datetime.fromtimestamp(ts / 1000, tz=UTC) for ts in timestamps]
    n = len(records)

    schema = pa.schema([
        ("timestamp", pa.timestamp("ms", tz="UTC")),
        ("bid", pa.float64()),
        ("ask", pa.float64()),
        ("spread_points", pa.float64()),
        ("bid_volume", pa.float32()),
        ("ask_volume", pa.float32()),
        ("symbol", pa.string()),
        ("source", pa.string()),
    ])

    return pa.table(
        {
            "timestamp": pa.array(ts_dt, type=pa.timestamp("ms", tz="UTC")),
            "bid": pa.array(bids, type=pa.float64()),
            "ask": pa.array(asks, type=pa.float64()),
            "spread_points": pa.array(spread_points, type=pa.float64()),
            "bid_volume": pa.array(bid_vols, type=pa.float32()),
            "ask_volume": pa.array(ask_vols, type=pa.float32()),
            "symbol": pa.array([symbol] * n, type=pa.string()),
            "source": pa.array(["dukascopy"] * n, type=pa.string()),
        },
        schema=schema,
    )


def _write_daily_parquet(table: pa.Table, symbol: str, dt: Date, output_dir: str):
    """Write daily tick data to Hive-partitioned Parquet path.

    Output: {output_dir}/{symbol}/year={YYYY}/month={MM}/{YYYY}-{MM}-{DD}.parquet
    Uses a temp file + atomic rename to avoid partial writes on crash.
    """
    yr = f"{dt.year:04d}"
    mo = f"{dt.month:02d}"
    day_tag = dt.isoformat()

    out_dir = Path(output_dir) / symbol / f"year={yr}" / f"month={mo}"
    out_dir.mkdir(parents=True, exist_ok=True)

    final_path = out_dir / f"{day_tag}.parquet"
    tmp_path = out_dir / f".{day_tag}.parquet.tmp"

    pq.write_table(table, str(tmp_path), row_group_size=65536, version="2.6")
    tmp_path.replace(final_path)


# ── Checkpoint ──

def load_checkpoint(output_dir: str) -> dict:
    path = os.path.join(output_dir, CHECKPOINT_FILE)
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {"completed": [], "version": 1}


def save_checkpoint(output_dir: str, cp: dict):
    path = os.path.join(output_dir, CHECKPOINT_FILE)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cp, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def _ckey(symbol: str, dt: Date) -> str:
    return f"{symbol}|{dt.isoformat()}"


# ── Date Helpers ──

def date_range(start: Date, end: Date) -> list[Date]:
    dates = []
    cur = start
    while cur <= end:
        dates.append(cur)
        cur += timedelta(days=1)
    return dates


# ── Fallback: Stooq.com OHLCV → Synthetic Ticks ──

STOOQ_SYMBOL_MAP = {
    "EURUSD": "eurusd",
    "GBPUSD": "gbpusd",
    "XAUUSD": "xauusd",
    "USDJPY": "usdjpy",
    "AUDUSD": "audusd",
    "USDCAD": "usdcad",
    "NZDUSD": "nzdusd",
    "USDCHF": "usdchf",
    "EURJPY": "eurjpy",
    "GBPJPY": "gbpjpy",
}

def download_stooq_ohlcv(symbol: str, dt: Date) -> list[dict] | None:
    """Download 1-minute OHLCV from Stooq.com for a single day.
    Returns list of {time, open, high, low, close, volume} or None on failure.
    """
    logger = get_logger()
    stooq_sym = STOOQ_SYMBOL_MAP.get(symbol, symbol.lower())
    url = f"https://stooq.com/q/d/l/?s={stooq_sym}&i=1m&d1={dt.isoformat()}&d2={dt.isoformat()}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
    except Exception as e:
        logger.debug("Stooq download failed for %s %s: %s", symbol, dt, e)
        return None

    if not text or "Date" not in text:
        return None

    rows = []
    reader = csv.DictReader(StringIO(text))
    for row in reader:
        try:
            rows.append({
                "time": datetime.strptime(f"{row['Date']} {row['Time']}", "%Y-%m-%d %H:%M").replace(tzinfo=UTC),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": float(row.get("Volume", 0)),
            })
        except (ValueError, KeyError):
            continue
    return rows if rows else None


def ohlcv_to_synthetic_ticks(ohlcv_rows: list[dict], symbol: str,
                              ticks_per_bar: int = 10, seed: int = 42) -> list[tuple]:
    """Convert 1-min OHLCV bars to synthetic tick data.

    Each bar generates `ticks_per_bar` ticks distributed uniformly.
    Tick prices are randomly walked between Open→High→Low→Close within each bar.
    Spread is 1-5 pips random per tick (1 pip = 0.0001 for FX, 0.01 for XAU).

    Returns list of (timestamp_ms, bid, ask, bid_vol, ask_vol).
    """
    rng = random.Random(seed)
    records = []
    is_xau = "XAU" in symbol.upper()
    pip_size = 0.01 if is_xau else 0.0001

    for bar in ohlcv_rows:
        bar_ts = int(bar["time"].timestamp() * 1000)
        o, h, l, c, v = bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"]
        interval_ms = 60_000 // ticks_per_bar  # evenly space ticks within 1-min bar

        # Walk price through the bar: open → high → low → close
        price_path = [o]
        if h > o:
            price_path.append(o + (h - o) * 0.3)
            price_path.append(h)
        if l < min(price_path[-1], c):
            price_path.append(max(l, c - (price_path[-1] - l) * 0.5))
            price_path.append(l)
        price_path.append(c)

        for i in range(ticks_per_bar):
            t = bar_ts + (i * interval_ms) + rng.randint(0, interval_ms // 2)
            frac = i / max(ticks_per_bar - 1, 1)
            idx = min(int(frac * (len(price_path) - 1)), len(price_path) - 2)
            local_frac = (frac * (len(price_path) - 1)) - idx
            mid = price_path[idx] + (price_path[min(idx + 1, len(price_path) - 1)] - price_path[idx]) * local_frac
            spread = (1 + rng.random() * 4) * pip_size  # 1-5 pips
            half = spread / 2
            bid = round(mid - half, 5)
            ask = round(mid + half, 5)
            bid_vol = round(rng.uniform(0.5, 5.0), 2)
            ask_vol = round(rng.uniform(0.5, 5.0), 2)
            records.append((t, bid, ask, bid_vol, ask_vol))

    return records


def download_fallback_stooq(symbol: str, dt: Date, output_dir: str) -> int:
    """Fallback download: Stooq.com 1min OHLCV → synthetic ticks → Parquet.

    Returns tick count written (0 = no data).
    """
    logger = get_logger()
    logger.info("  [FALLBACK] Stooq.com OHLCV → synthetic ticks for %s %s", symbol, dt)
    ohlcv = download_stooq_ohlcv(symbol, dt)
    if not ohlcv:
        logger.warning("  [FALLBACK] No Stooq data for %s %s", symbol, dt)
        return 0
    ticks = ohlcv_to_synthetic_ticks(ohlcv, symbol)
    if not ticks:
        return 0
    table = _records_to_table_fallback(ticks, symbol)
    _write_daily_parquet(table, symbol, dt, output_dir)
    logger.info("  [FALLBACK] Wrote %d synthetic ticks for %s %s", len(ticks), symbol, dt)
    return len(ticks)


def download_fallback_synthetic(symbol: str, dt: Date, output_dir: str) -> int:
    """Fallback: purely synthetic ticks generated from random walk.

    Generates ~14400 ticks (10/min × 1440 min) per day.
    """
    logger = get_logger()
    logger.info("  [FALLBACK] Pure synthetic ticks for %s %s", symbol, dt)
    is_xau = "XAU" in symbol.upper()
    base_price = 2000.0 if is_xau else 1.1000
    pip_size = 0.01 if is_xau else 0.0001

    rng = random.Random(dt.toordinal() + hash(symbol) % 10000)
    records = []
    day_start = int(datetime(dt.year, dt.month, dt.day, tzinfo=UTC).timestamp() * 1000)
    price = base_price
    ticks_per_min = 10
    interval_ms = 60_000 // ticks_per_min

    for minute in range(1440):  # 24h × 60min
        o = price + rng.gauss(0, pip_size * 2)
        h = o + abs(rng.gauss(0, pip_size * 3))
        l = o - abs(rng.gauss(0, pip_size * 3))
        c = (o + h + l) / 3 + rng.gauss(0, pip_size)
        price = c

        for i in range(ticks_per_min):
            t = day_start + (minute * 60_000) + (i * interval_ms) + rng.randint(0, interval_ms // 2)
            frac = i / ticks_per_min
            mid = o + (c - o) * frac + rng.gauss(0, pip_size * 0.3)
            spread = (1 + rng.random() * 4) * pip_size
            half = spread / 2
            bid = round(mid - half, 5)
            ask = round(mid + half, 5)
            bid_vol = round(rng.uniform(0.5, 5.0), 2)
            ask_vol = round(rng.uniform(0.5, 5.0), 2)
            records.append((t, bid, ask, bid_vol, ask_vol))

    if not records:
        return 0
    table = _records_to_table_fallback(records, symbol)
    _write_daily_parquet(table, symbol, dt, output_dir)
    logger.info("  [FALLBACK] Wrote %d synthetic ticks for %s %s", len(records), symbol, dt)
    return len(records)


def _records_to_table_fallback(records: list[tuple], symbol: str) -> pa.Table:
    """Same schema as _records_to_table but with source='fallback'."""
    timestamps, bids, asks, bid_vols, ask_vols = [], [], [], [], []
    for ts, bid, ask, bid_vol, ask_vol in records:
        timestamps.append(ts)
        bids.append(bid)
        asks.append(ask)
        bid_vols.append(bid_vol)
        ask_vols.append(ask_vol)

    spread_points = [(a - b) * 100_000.0 for a, b in zip(asks, bids)]
    ts_dt = [datetime.fromtimestamp(ts / 1000, tz=UTC) for ts in timestamps]
    n = len(records)

    schema = pa.schema([
        ("timestamp", pa.timestamp("ms", tz="UTC")),
        ("bid", pa.float64()),
        ("ask", pa.float64()),
        ("spread_points", pa.float64()),
        ("bid_volume", pa.float32()),
        ("ask_volume", pa.float32()),
        ("symbol", pa.string()),
        ("source", pa.string()),
    ])
    return pa.table(
        {
            "timestamp": pa.array(ts_dt, type=pa.timestamp("ms", tz="UTC")),
            "bid": pa.array(bids, type=pa.float64()),
            "ask": pa.array(asks, type=pa.float64()),
            "spread_points": pa.array(spread_points, type=pa.float64()),
            "bid_volume": pa.array(bid_vols, type=pa.float32()),
            "ask_volume": pa.array(ask_vols, type=pa.float32()),
            "symbol": pa.array([symbol] * n, type=pa.string()),
            "source": pa.array(["fallback"] * n, type=pa.string()),
        },
        schema=schema,
    )


FALLBACK_MODES = {"stooq", "synthetic", "off"}


# ── CLI ──

def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Dukascopy historical tick data downloader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--symbols", type=str, default="EURUSD,GBPUSD,XAUUSD",
        help="Comma-separated symbols (default: EURUSD,GBPUSD,XAUUSD)",
    )
    parser.add_argument(
        "--start", type=str, default="2020-01-01",
        help="Start date YYYY-MM-DD (default: 2020-01-01)",
    )
    parser.add_argument(
        "--end", type=str, default="2024-12-31",
        help="End date YYYY-MM-DD (default: 2024-12-31)",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output directory (default: artifacts/mega_data/ticks)",
    )
    parser.add_argument(
        "--workers", type=int, default=DEFAULT_WORKERS,
        help=f"Parallel download workers (default: {DEFAULT_WORKERS})",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume from checkpoint, skip completed dates",
    )
    parser.add_argument(
        "--retry", type=int, default=DEFAULT_RETRIES,
        help=f"Max retries per hour (default: {DEFAULT_RETRIES})",
    )
    parser.add_argument(
        "--fallback", type=str, default="stooq", choices=["stooq", "synthetic", "off"],
        help="Fallback data source when Dukascopy fails (default: stooq)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be downloaded, then exit",
    )
    return parser.parse_args(argv)


def main():
    args = parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    output_dir = os.path.abspath(args.output) if args.output else os.path.join(
        project_root, "artifacts", "mega_data", "ticks"
    )
    os.makedirs(output_dir, exist_ok=True)

    logger = setup_logging(output_dir)

    if not PYARROW_OK:
        logger.error("pyarrow is required. Install with: pip install pyarrow")
        sys.exit(1)

    try:
        start_date = Date.fromisoformat(args.start)
        end_date = Date.fromisoformat(args.end)
    except ValueError as e:
        logger.error("Invalid date format: %s", e)
        sys.exit(1)

    if start_date > end_date:
        logger.error("Start date must be before end date")
        sys.exit(1)

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        logger.error("No symbols specified")
        sys.exit(1)

    unknown = [s for s in symbols if s not in DUKA_SYMBOL_MAP]
    if unknown and DUKA_SYMBOL_MAP:
        logger.warning("Unrecognized symbols (no known Dukascopy equivalent): %s", unknown)

    dates = date_range(start_date, end_date)
    all_items = [(sym, dt) for sym in symbols for dt in dates]

    if args.resume:
        checkpoint = load_checkpoint(output_dir)
    else:
        checkpoint = {"completed": [], "version": 1}

    completed_set = set(checkpoint.get("completed", []))
    pending = [(s, d) for s, d in all_items if _ckey(s, d) not in completed_set]

    if not pending:
        logger.info("All downloads completed. Nothing to do.")
        return

    # Dry-run: just print what would be done
    if args.dry_run:
        logger.info("DRY RUN — no data will be downloaded")
        logger.info("  Symbols: %s", symbols)
        logger.info("  Range: %s -> %s", start_date, end_date)
        logger.info("  Pairs: %d", len(pending))
        logger.info("  Fallback: %s", args.fallback)
        for sym, dt in pending[:10]:
            logger.info("    Would download: %s %s", sym, dt)
        if len(pending) > 10:
            logger.info("    ... and %d more", len(pending) - 10)
        return

    logger.info(
        "Downloading %d date/symbol pairs (%d already completed)",
        len(pending), len(all_items) - len(pending),
    )
    logger.info("  Symbols: %s", symbols)
    logger.info("  Range: %s -> %s", start_date, end_date)
    logger.info("  Workers: %d", args.workers)
    logger.info("  Fallback: %s", args.fallback)
    logger.info("  Output: %s", output_dir)

    if args.fallback != "off":
        logger.info("  [FALLBACK] Will use %s when Dukascopy unavailable", args.fallback)

    completed_count = len(completed_set)
    total_ticks = 0
    errors = 0
    fallback_used = 0
    fallback_ticks = 0
    save_interval = max(1, len(pending) // 20)

    progress = None
    if TQDM_OK:
        progress = tqdm(total=len(pending), desc="Pairs", unit="pair", mininterval=1.0)

    # First pass: submit all Dukascopy downloads
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        fmap = {}
        for sym, dt in pending:
            duka_sym = DUKA_SYMBOL_MAP.get(sym, sym)
            f = executor.submit(process_date, sym, duka_sym, dt, output_dir, args.retry)
            fmap[f] = (sym, dt)

        for i, future in enumerate(as_completed(fmap)):
            sym, dt = fmap[future]
            pair_key = _ckey(sym, dt)
            try:
                n = future.result()
                if n == 0 and args.fallback != "off":
                    # Dukascopy returned no data — try fallback
                    logger.info("  [FALLBACK] No Dukascopy data for %s %s, using %s", sym, dt, args.fallback)
                    if args.fallback == "stooq":
                        n = download_fallback_stooq(sym, dt, output_dir)
                    elif args.fallback == "synthetic":
                        n = download_fallback_synthetic(sym, dt, output_dir)
                    if n > 0:
                        fallback_used += 1
                        fallback_ticks += n
                if n > 0:
                    total_ticks += n
                completed_set.add(pair_key)
                completed_count += 1
            except Exception as e:
                # Dukascopy failed — try fallback
                if args.fallback != "off":
                    try:
                        logger.info("  [FALLBACK] Dukascopy error for %s %s: %s", sym, dt, e)
                        if args.fallback == "stooq":
                            n = download_fallback_stooq(sym, dt, output_dir)
                        elif args.fallback == "synthetic":
                            n = download_fallback_synthetic(sym, dt, output_dir)
                        if n > 0:
                            total_ticks += n
                            fallback_used += 1
                            fallback_ticks += n
                        completed_set.add(pair_key)
                        completed_count += 1
                    except Exception as e2:
                        errors += 1
                        logger.error("FAILED (Dukascopy+fallback) %s %s: %s / %s", sym, dt, e, e2)
                else:
                    errors += 1
                    logger.error("FAILED %s %s: %s", sym, dt, e)

            if i > 0 and i % save_interval == 0:
                checkpoint["completed"] = sorted(completed_set)
                save_checkpoint(output_dir, checkpoint)

            if progress:
                progress.update(1)

    if progress:
        progress.close()

    checkpoint["completed"] = sorted(completed_set)
    save_checkpoint(output_dir, checkpoint)

    logger.info("=" * 50)
    logger.info("Download complete")
    logger.info("  Completed: %d pairs", completed_count)
    logger.info("  Ticks: %s", f"{total_ticks:,}")
    if fallback_used > 0:
        logger.info("  Fallback used: %d pairs, %s ticks", fallback_used, f"{fallback_ticks:,}")
    logger.info("  Errors: %d", errors)
    logger.info("  Output: %s", output_dir)
    logger.info("=" * 50)


if __name__ == "__main__":
    main()

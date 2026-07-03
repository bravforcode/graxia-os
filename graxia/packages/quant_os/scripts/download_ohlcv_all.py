"""Download OHLCV data for multiple symbols and timeframes from free sources.

Sources:
  - Crypto (BTCUSD, ETHUSD): Binance spot public API (/api/v3/klines)
  - FX (XAUUSD, EURUSD): Stooq.com free CSV downloads

Usage:
    python scripts/download_ohlcv_all.py --symbols XAUUSD EURUSD BTCUSD ETHUSD --timeframes M1 M5 M15 H1 --start 2017-01-01
    python scripts/download_ohlcv_all.py --symbols BTCUSD ETHUSD --timeframes M1 M5 --start 2020-01-01 --end 2024-12-31
    python scripts/download_ohlcv_all.py --symbols XAUUSD --timeframes H1 --start 2020-01-01 --dry-run

Output:
    data/{SYMBOL}_{TIMEFRAME}.csv  with columns: time, open, high, low, close, volume

Features:
    - Deduplicates by timestamp when merging with existing CSVs
    - Resumes by skipping files with sufficient existing data
    - Rate-limited requests (Binance 0.06s, Stooq 0.02s)
    - Retry with exponential backoff (3 attempts)
    - Progress logging every 10 pages
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"

# ── Logging ───────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────

COLUMNS = ["time", "open", "high", "low", "close", "volume"]

# Binance
BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_CANDLE_LIMIT = 1000
BINANCE_SLEEP = 0.06  # seconds between requests (~16 req/s, well under 1200 weight/min)

# Stooq
STOOQ_SLEEP = 0.02  # seconds between requests

# Symbol mappings
# Binance uses BTCUSDT/ETHUSDT; we store as BTCUSD/ETHUSD
CRYPTO_TO_BINANCE = {
    "BTCUSD": "BTCUSDT",
    "ETHUSD": "ETHUSDT",
}
BINANCE_TO_CRYPTO = {v: k for k, v in CRYPTO_TO_BINANCE.items()}

# Stooq uses lowercase pair names
FX_TO_STOOQ = {
    "XAUUSD": "xauusd",
    "EURUSD": "eurusd",
    "GBPUSD": "gbpusd",
    "USDJPY": "usdjpy",
    "AUDUSD": "audusd",
    "USDCAD": "usdcad",
    "USDCHF": "usdchf",
    "NZDUSD": "nzdusd",
}

# Timeframe mappings
TF_TO_BINANCE_INTERVAL = {
    "M1": "1m",
    "M5": "5m",
    "M15": "15m",
    "H1": "1h",
}

TF_TO_STOOQ_INTERVAL = {
    "M1": "m1",
    "M5": "m5",
    "M15": "m15",
    "H1": "h1",
}

# Minutes per candle (for computing date ranges from candle count)
TF_MINUTES = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "H1": 60,
}


# ── Helpers ───────────────────────────────────────────────────────────

def to_ms(dt: datetime) -> int:
    """Convert datetime to milliseconds since epoch."""
    return int(dt.timestamp() * 1000)


def from_ms(ms: int) -> datetime:
    """Convert milliseconds since epoch to UTC datetime."""
    return datetime.fromtimestamp(ms / 1000.0, tz=UTC)


def parse_date(s: str) -> datetime:
    """Parse YYYY-MM-DD string to UTC datetime."""
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC)


def symbol_type(symbol: str) -> str:
    """Classify symbol as 'crypto' or 'fx'."""
    if symbol in CRYPTO_TO_BINANCE:
        return "crypto"
    return "fx"


def output_path(symbol: str, timeframe: str) -> Path:
    """Get output CSV path for a symbol/timeframe."""
    return DATA_DIR / f"{symbol}_{timeframe}.csv"


def get_existing_range(path: Path) -> tuple[str | None, str | None]:
    """Read existing CSV and return (min_time, max_time) or (None, None)."""
    if not path.exists():
        return None, None
    try:
        df = pd.read_csv(path, usecols=["time"], dtype={"time": str})
        if df.empty:
            return None, None
        return df["time"].min(), df["time"].max()
    except Exception as e:
        logger.warning("Could not read existing file %s: %s", path, e)
        return None, None


def should_skip(path: Path, start: datetime, timeframe: str) -> bool:
    """Check if we should skip downloading (existing data covers the range)."""
    if not path.exists():
        return False
    try:
        df = pd.read_csv(path, usecols=["time"], dtype={"time": str})
        if df.empty:
            return False
        min_time = df["time"].min()
        max_time = df["time"].max()
        # If existing data starts at or before our start date, skip
        earliest_existing = pd.to_datetime(min_time)
        start_dt = pd.to_datetime(start.strftime("%Y-%m-%d %H:%M:%S"))
        if earliest_existing <= start_dt:
            logger.info("  SKIP: %s already has data from %s (covers start %s)",
                        path.name, min_time, start.date())
            return True
    except Exception:
        pass
    return False


def merge_with_existing(df: pd.DataFrame, path: Path) -> pd.DataFrame:
    """Merge newly downloaded rows with existing CSV, deduplicate, sort."""
    if not path.exists():
        return df
    try:
        existing = pd.read_csv(path)
        combined = pd.concat([existing, df], ignore_index=True)
        combined.drop_duplicates(subset=["time"], keep="last", inplace=True)
        combined.sort_values("time", inplace=True)
        combined.reset_index(drop=True, inplace=True)
        logger.info("  Merged %d new rows with %d existing -> %d total",
                     len(df), len(existing), len(combined))
        return combined
    except Exception as e:
        logger.warning("Could not merge with existing %s: %s", path, e)
        return df


# ── Binance Download ──────────────────────────────────────────────────

def fetch_binance_klines(symbol: str, interval: str, start_ms: int, end_ms: int) -> list[list]:
    """Fetch one page of klines from Binance spot API."""
    url = (
        f"{BINANCE_KLINES_URL}?symbol={symbol}&interval={interval}"
        f"&startTime={start_ms}&endTime={end_ms}&limit={BINANCE_CANDLE_LIMIT}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "quant_os-ohlcv-all/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                logger.warning("Binance rate limit (429), backing off 2s")
                time.sleep(2.0)
            elif e.code == 418:
                logger.warning("Binance IP ban (418), backing off 5s")
                time.sleep(5.0)
            else:
                logger.warning("Binance HTTP %d for %s (attempt %d/3): %s",
                               e.code, symbol, attempt + 1, e.reason)
                time.sleep(0.5 * (attempt + 1))
        except Exception as e:
            logger.warning("Binance error for %s (attempt %d/3): %s",
                           symbol, attempt + 1, e)
            time.sleep(0.5 * (attempt + 1))
    return []


def download_binance(symbol: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame:
    """Download all klines from Binance for a symbol/timeframe/date range.

    Binance uses BTCUSDT/ETHUSDT; we map back to BTCUSD/ETHUSD for output.
    Pagination advances by 1000 candles per interval.
    """
    binance_sym = CRYPTO_TO_BINANCE.get(symbol, symbol)
    interval = TF_TO_BINANCE_INTERVAL[timeframe]
    minutes_per_candle = TF_MINUTES[timeframe]

    logger.info("  Binance: %s (%s) %s from %s to %s",
                binance_sym, interval, timeframe, start.date(), end.date())

    all_rows: list[list] = []
    current = start
    page = 0

    while current < end:
        # Calculate end of this batch (1000 candles from current)
        batch_end = min(
            current + timedelta(minutes=BINANCE_CANDLE_LIMIT * minutes_per_candle),
            end,
        )
        start_ms = to_ms(current)
        end_ms = to_ms(batch_end)

        rows = fetch_binance_klines(binance_sym, interval, start_ms, end_ms)
        if not rows:
            # No data for this period; try advancing by the batch size
            # (Binance may not have data this far back)
            next_start = current + timedelta(minutes=BINANCE_CANDLE_LIMIT * minutes_per_candle)
            if next_start <= current:
                break
            if page == 0:
                logger.info("  No data at %s, advancing to find earliest available...", current.date())
            current = next_start
            page += 1
            continue

        for row in rows:
            all_rows.append([
                from_ms(row[0]).strftime("%Y-%m-%d %H:%M:%S"),
                float(row[1]),  # open
                float(row[2]),  # high
                float(row[3]),  # low
                float(row[4]),  # close
                float(row[5]),  # volume
            ])

        # Advance: use last candle's close time + 1ms
        last_close_ms = rows[-1][6]
        next_start = from_ms(last_close_ms) + timedelta(milliseconds=1)
        if next_start <= current:
            break
        current = next_start
        page += 1

        if page % 10 == 0:
            logger.info("    page %d, %d rows so far, current date: %s",
                        page, len(all_rows), current.date())
        time.sleep(BINANCE_SLEEP)

    logger.info("  Binance done: %d rows total", len(all_rows))
    df = pd.DataFrame(all_rows, columns=COLUMNS)
    if not df.empty:
        df.drop_duplicates(subset=["time"], keep="first", inplace=True)
        df.sort_values("time", inplace=True)
        df.reset_index(drop=True, inplace=True)
    return df


# ── Stooq Download ────────────────────────────────────────────────────

def fetch_stooq_csv(stooq_symbol: str, interval: str, d1: str, d2: str) -> str | None:
    """Download CSV from Stooq.com.

    URL format: https://stooq.com/q/d/l/?s={symbol}&d1={YYYYMMDD}&d2={YYYYMMDD}&i={interval}
    Returns raw CSV text or None on failure.
    """
    url = (
        f"https://stooq.com/q/d/l/?s={stooq_symbol}"
        f"&d1={d1}&d2={d2}&i={interval}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                text = resp.read().decode("utf-8")
                if "No data" in text or "Error" in text or "<html" in text.lower() or "<!doctype" in text.lower():
                    logger.debug("Stooq returned no data/HTML for %s (%s-%s)",
                                 stooq_symbol, d1, d2)
                    return None
                return text
        except urllib.error.HTTPError as e:
            if e.code == 429:
                logger.warning("Stooq rate limit (429), backing off 2s")
                time.sleep(2.0)
            else:
                logger.warning("Stooq HTTP %d for %s (attempt %d/3): %s",
                               e.code, stooq_symbol, attempt + 1, e.reason)
                time.sleep(0.5 * (attempt + 1))
        except Exception as e:
            logger.warning("Stooq error for %s (attempt %d/3): %s",
                           stooq_symbol, attempt + 1, e)
            time.sleep(0.5 * (attempt + 1))
    return None


def download_stooq(symbol: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame:
    """Download OHLCV from Stooq.com for an FX symbol.

    Stooq supports date-range CSV downloads. We split into monthly chunks
    to avoid timeouts and get better error handling.
    """
    stooq_sym = FX_TO_STOOQ.get(symbol, symbol.lower())
    interval = TF_TO_STOOQ_INTERVAL[timeframe]

    logger.info("  Stooq: %s (%s) %s from %s to %s",
                stooq_sym, interval, timeframe, start.date(), end.date())

    all_rows: list[dict] = []
    # Download in monthly chunks to avoid large single downloads
    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + timedelta(days=30), end)
        d1 = chunk_start.strftime("%Y%m%d")
        d2 = chunk_end.strftime("%Y%m%d")

        text = fetch_stooq_csv(stooq_sym, interval, d1, d2)
        if text:
            rows = _parse_stooq_csv(text)
            all_rows.extend(rows)

        chunk_start = chunk_end + timedelta(days=1)
        time.sleep(STOOQ_SLEEP)

    logger.info("  Stooq done: %d rows total", len(all_rows))

    if not all_rows:
        return pd.DataFrame(columns=COLUMNS)

    df = pd.DataFrame(all_rows)
    df.drop_duplicates(subset=["time"], keep="first", inplace=True)
    df.sort_values("time", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def _parse_stooq_csv(text: str) -> list[dict]:
    """Parse Stooq CSV text into list of dicts with COLUMNS format."""
    rows = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        try:
            # Stooq returns Date and optionally Time columns
            date_str = row.get("Date", "").strip()
            time_str = row.get("Time", "").strip()

            if time_str:
                dt_str = f"{date_str} {time_str}"
                dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
            else:
                dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)

            rows.append({
                "time": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": float(row.get("Volume", 0)),
            })
        except (ValueError, KeyError):
            continue
    return rows


# ── Main Download Dispatcher ──────────────────────────────────────────

def download_symbol_timeframe(symbol: str, timeframe: str,
                              start: datetime, end: datetime,
                              dry_run: bool = False, force: bool = False) -> pd.DataFrame:
    """Download data for one symbol+timeframe, handling merge and resume."""
    out = output_path(symbol, timeframe)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Check if we should skip (unless --force)
    if not force and should_skip(out, start, timeframe):
        return pd.DataFrame()

    stype = symbol_type(symbol)

    if dry_run:
        min_t, max_t = get_existing_range(out)
        logger.info("  DRY RUN: %s %s -> %s (existing: %s to %s)",
                     symbol, timeframe, out, min_t, max_t)
        return pd.DataFrame()

    # Download from appropriate source
    if stype == "crypto":
        df = download_binance(symbol, timeframe, start, end)
    else:
        df = download_stooq(symbol, timeframe, start, end)

    if df.empty:
        logger.warning("  No data downloaded for %s %s", symbol, timeframe)
        return df

    # Merge with existing
    df = merge_with_existing(df, out)

    # Save
    df.to_csv(out, index=False)
    logger.info("  Saved %d rows to %s (range: %s to %s)",
                len(df), out.name, df["time"].min(), df["time"].max())
    return df


# ── CLI ───────────────────────────────────────────────────────────────

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download OHLCV data from Binance (crypto) and Stooq (FX)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--symbols", nargs="+",
        default=["XAUUSD", "EURUSD", "BTCUSD", "ETHUSD"],
        help="Symbols to download (default: XAUUSD EURUSD BTCUSD ETHUSD)",
    )
    parser.add_argument(
        "--timeframes", nargs="+",
        default=["M1", "M5", "M15", "H1"],
        help="Timeframes to download (default: M1 M5 M15 H1)",
    )
    parser.add_argument(
        "--start", type=str, default="2017-01-01",
        help="Start date YYYY-MM-DD (default: 2017-01-01)",
    )
    parser.add_argument(
        "--end", type=str, default=None,
        help="End date YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be downloaded without downloading",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-download even if file exists and covers the range",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()

    start = parse_date(args.start)
    end = parse_date(args.end) if args.end else datetime.now(UTC)
    # Include end date fully by adding 1 day
    end = end + timedelta(days=1)

    if start >= end:
        logger.error("Start date must be before end date")
        return 1

    symbols = [s.upper() for s in args.symbols]
    timeframes = [tf.upper() for tf in args.timeframes]

    # Validate symbols
    for sym in symbols:
        if sym not in CRYPTO_TO_BINANCE and sym not in FX_TO_STOOQ:
            logger.warning("Unknown symbol '%s' — will attempt Stooq download", sym)

    # Validate timeframes
    for tf in timeframes:
        if tf not in TF_TO_BINANCE_INTERVAL:
            logger.error("Unsupported timeframe '%s'. Supported: %s",
                         tf, list(TF_TO_BINANCE_INTERVAL.keys()))
            return 1

    logger.info("=" * 60)
    logger.info("OHLCV All-in-One Downloader")
    logger.info("=" * 60)
    logger.info("  Symbols:     %s", symbols)
    logger.info("  Timeframes:  %s", timeframes)
    logger.info("  Date range:  %s to %s", start.date(), (end - timedelta(days=1)).date())
    logger.info("  Dry run:     %s", args.dry_run)
    logger.info("  Force:       %s", args.force)
    logger.info("  Output dir:  %s", DATA_DIR)
    logger.info("=" * 60)

    total_rows = 0
    total_files = 0
    skipped = 0
    errors = 0

    for sym in symbols:
        stype = symbol_type(sym)
        logger.info("\n--- %s (%s) ---", sym, stype.upper())

        for tf in timeframes:
            logger.info("  [%s/%s]", sym, tf)
            try:
                df = download_symbol_timeframe(
                    sym, tf, start, end, dry_run=args.dry_run, force=args.force
                )
                if not df.empty:
                    total_rows += len(df)
                    total_files += 1
                elif not args.dry_run:
                    skipped += 1
            except Exception as e:
                logger.error("  ERROR downloading %s %s: %s", sym, tf, e)
                errors += 1

    logger.info("\n" + "=" * 60)
    logger.info("Summary")
    logger.info("=" * 60)
    logger.info("  Files written: %d", total_files)
    logger.info("  Total rows:    %s", f"{total_rows:,}")
    logger.info("  Skipped:       %d (already have data)", skipped)
    logger.info("  Errors:        %d", errors)
    logger.info("=" * 60)

    return 1 if errors > 0 else 0


if __name__ == "__main__":
    sys.exit(main())

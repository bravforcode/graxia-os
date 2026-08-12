"""Unified data pipeline — single entry point for all data operations.

Usage:
    python scripts/data_pipeline.py pull --all
    python scripts/data_pipeline.py pull --symbols XAUUSD EURUSD BTCUSD ETHUSD --timeframes D1 M15 H1
    python scripts/data_pipeline.py pull --source binance --symbols BTCUSD --timeframes M1 M5 M15 H1
    python scripts/data_pipeline.py status
    python scripts/data_pipeline.py ingest --dump-dir "C:/path/to/stooq_dump"
    python scripts/data_pipeline.py pull --source fred

Sources (auto-routed):
    binance  → BTCUSD, ETHUSD  (M1/M5/M15/H1) — free, no key
    stooq    → FX pairs         (M1/M5/M15/H1) — free, no key (may be blocked)
    yfinance → all              (D1)            — free, no key
    fred     → macro series     (D1)            — free, needs FRED_API_KEY env var
    cot      → gold/silver      (W1)            — free, needs cot_reports package
    stooq_dump → all            (D1)            — offline, needs pre-downloaded dump
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import os
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
MACRO_DIR = DATA_DIR / "market_data" / "fred"
COT_DIR = DATA_DIR / "market_data" / "cot"

# Load .env if available
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass  # python-dotenv not installed; rely on OS env vars

# ── Logging ───────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────

COLUMNS = ["time", "open", "high", "low", "close", "volume"]

# Source routing
CRYPTO_SYMBOLS = {"BTCUSD", "ETHUSD"}
FX_SYMBOLS = {
    "XAUUSD", "EURUSD", "GBPUSD", "USDJPY",
    "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "XAGUSD",
}
INDEX_SYMBOLS = {"US30", "NAS100", "SPX500", "DAX40", "FTSE100", "NK225"}
INTRADAY_TFS = {"M1", "M5", "M15", "M30", "H1", "H4"}

# Binance
BINANCE_URL = "https://api.binance.com/api/v3/klines"
BINANCE_LIMIT = 1000
BINANCE_SLEEP = 0.06
CRYPTO_TO_BINANCE = {"BTCUSD": "BTCUSDT", "ETHUSD": "ETHUSDT"}
TF_TO_BINANCE = {"M1": "1m", "M5": "5m", "M15": "15m", "H1": "1h"}

# Stooq
STOOQ_SLEEP = 0.02
FX_TO_STOOQ = {
    "XAUUSD": "xauusd", "EURUSD": "eurusd", "GBPUSD": "gbpusd",
    "USDJPY": "usdjpy", "AUDUSD": "audusd", "USDCAD": "usdcad",
    "USDCHF": "usdchf", "NZDUSD": "nzdusd", "XAGUSD": "xagusd",
}
TF_TO_STOOQ = {"M1": "m1", "M5": "m5", "M15": "m15", "H1": "h1"}

# FRED
FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_SERIES = {
    "interest_rates": ["DFII10", "DGS10", "DGS2", "DGS30", "DGS5", "DGS7", "DGS3MO", "DGS6MO", "T5YIE", "T5YIFR", "T10YIE", "T10Y2Y"],
    "gold_volatility": ["GVZCLS", "VIXCLS"],
    "oil": ["DCOILWTICO", "DCOILBRENTEU"],
    "dollar": ["DTWEXBGS"],
    "fx": ["DEXUSEU", "DEXJPUS"],
    "economic": ["UNRATE", "CPIAUCSL", "CPILFESL", "FEDFUNDS", "INDPRO", "UMCSENT"],
    "credit": ["BAMLH0A0HYM2", "BAMLH0A0HYM2EY", "BAMLH0A1HYBB", "TEDRATE", "BAA10Y"],
    "liquidity": ["WALCL", "BOGMBASE", "RRPONTSYD", "WTREGEN"],
}

# Yahoo Finance
YF_TICKERS = {
    "XAUUSD": "GC=F", "XAGUSD": "SI=F", "US30": "^DJI", "NAS100": "^IXIC",
    "SPX500": "^GSPC", "BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD",
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "JPY=X",
}


# ── Helpers ───────────────────────────────────────────────────────────

def output_path(symbol: str, timeframe: str) -> Path:
    return DATA_DIR / f"{symbol}_{timeframe}.csv"


def merge_csv(new_df: pd.DataFrame, path: Path) -> pd.DataFrame:
    """Merge new data with existing CSV, deduplicate, sort."""
    if not path.exists() or new_df.empty:
        return new_df
    try:
        existing = pd.read_csv(path)
        if existing.empty:
            return new_df
        combined = pd.concat([existing, new_df], ignore_index=True)
        combined.drop_duplicates(subset=["time"], keep="last", inplace=True)
        combined.sort_values("time", inplace=True)
        combined.reset_index(drop=True, inplace=True)
        return combined
    except Exception as e:
        logger.warning("Merge failed for %s: %s", path.name, e)
        return new_df


def to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def from_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=UTC)


def http_get(url: str, timeout: int = 30, retries: int = 3) -> str | None:
    """HTTP GET with retry. Returns text or None."""
    req = urllib.request.Request(url, headers={"User-Agent": "quant_os-pipeline/1.0"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2.0)
            else:
                time.sleep(0.5 * (attempt + 1))
        except Exception:
            time.sleep(0.5 * (attempt + 1))
    return None


# ── Source: Binance ───────────────────────────────────────────────────

def pull_binance(symbol: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame:
    """Download OHLCV from Binance spot API."""
    binance_sym = CRYPTO_TO_BINANCE.get(symbol, symbol)
    interval = TF_TO_BINANCE.get(timeframe)
    if not interval:
        logger.warning("  Binance: unsupported timeframe %s", timeframe)
        return pd.DataFrame(columns=COLUMNS)

    minutes = {"M1": 1, "M5": 5, "M15": 15, "H1": 60}.get(timeframe, 1)
    logger.info("  Binance: %s (%s) %s from %s to %s", binance_sym, interval, timeframe, start.date(), end.date())

    all_rows = []
    current = start
    page = 0

    while current < end:
        batch_end = min(current + timedelta(minutes=BINANCE_LIMIT * minutes), end)
        url = f"{BINANCE_URL}?symbol={binance_sym}&interval={interval}&startTime={to_ms(current)}&endTime={to_ms(batch_end)}&limit={BINANCE_LIMIT}"
        text = http_get(url)
        if not text:
            # Skip forward if no data at this point
            current = batch_end
            page += 1
            continue

        rows = json.loads(text)
        if not rows:
            current = batch_end
            page += 1
            continue

        for row in rows:
            all_rows.append([
                from_ms(row[0]).strftime("%Y-%m-%d %H:%M:%S"),
                float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5]),
            ])

        last_close_ms = rows[-1][6]
        next_start = from_ms(last_close_ms) + timedelta(milliseconds=1)
        if next_start <= current:
            break
        current = next_start
        page += 1
        if page % 10 == 0:
            logger.info("    page %d, %d rows", page, len(all_rows))
        time.sleep(BINANCE_SLEEP)

    logger.info("  Binance done: %d rows", len(all_rows))
    if not all_rows:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.DataFrame(all_rows, columns=COLUMNS)
    df.drop_duplicates(subset=["time"], keep="first", inplace=True)
    df.sort_values("time", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


# ── Source: Stooq ─────────────────────────────────────────────────────

def pull_stooq(symbol: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame:
    """Download OHLCV from Stooq.com."""
    stooq_sym = FX_TO_STOOQ.get(symbol, symbol.lower())
    interval = TF_TO_STOOQ.get(timeframe)
    if not interval:
        logger.warning("  Stooq: unsupported timeframe %s", timeframe)
        return pd.DataFrame(columns=COLUMNS)

    logger.info("  Stooq: %s (%s) %s from %s to %s", stooq_sym, interval, timeframe, start.date(), end.date())

    all_rows = []
    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + timedelta(days=30), end)
        d1 = chunk_start.strftime("%Y%m%d")
        d2 = chunk_end.strftime("%Y%m%d")
        url = f"https://stooq.com/q/d/l/?s={stooq_sym}&d1={d1}&d2={d2}&i={interval}"
        text = http_get(url)
        if text and "<html" not in text.lower() and "<!doctype" not in text.lower():
            reader = csv.DictReader(io.StringIO(text))
            for row in reader:
                try:
                    date_str = row.get("Date", "").strip()
                    time_str = row.get("Time", "").strip()
                    if time_str:
                        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
                    else:
                        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
                    all_rows.append({
                        "time": dt.strftime("%Y-%m-%d %H:%M:%S"),
                        "open": float(row["Open"]), "high": float(row["High"]),
                        "low": float(row["Low"]), "close": float(row["Close"]),
                        "volume": float(row.get("Volume", 0)),
                    })
                except (ValueError, KeyError):
                    continue
        chunk_start = chunk_end + timedelta(days=1)
        time.sleep(STOOQ_SLEEP)

    logger.info("  Stooq done: %d rows", len(all_rows))
    if not all_rows:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.DataFrame(all_rows)
    df.drop_duplicates(subset=["time"], keep="first", inplace=True)
    df.sort_values("time", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


# ── Source: Yahoo Finance ─────────────────────────────────────────────

def pull_yfinance(symbol: str) -> pd.DataFrame:
    """Download daily OHLCV from Yahoo Finance."""
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("  yfinance not installed, skipping")
        return pd.DataFrame(columns=COLUMNS)

    ticker = YF_TICKERS.get(symbol)
    if not ticker:
        ticker = symbol.replace("USD", "=X").replace("=X=X", "=X")

    logger.info("  Yahoo: %s (%s) daily", symbol, ticker)
    try:
        t = yf.Ticker(ticker)
        df = t.history(period="max")
        if df.empty:
            logger.warning("  Yahoo: no data for %s", ticker)
            return pd.DataFrame(columns=COLUMNS)

        df = df.reset_index()
        df.rename(columns={"Date": "time", "Open": "open", "High": "high",
                           "Low": "low", "Close": "close", "Volume": "volume"}, inplace=True)
        df["time"] = pd.to_datetime(df["time"]).dt.strftime("%Y-%m-%d %H:%M:%S")
        df = df[COLUMNS]
        df.dropna(subset=["close"], inplace=True)
        df.drop_duplicates(subset=["time"], keep="first", inplace=True)
        df.sort_values("time", inplace=True)
        df.reset_index(drop=True, inplace=True)
        logger.info("  Yahoo done: %d rows", len(df))
        return df
    except Exception as e:
        logger.warning("  Yahoo error: %s", e)
        return pd.DataFrame(columns=COLUMNS)


# ── Source: FRED ──────────────────────────────────────────────────────

def pull_fred(start_date: str = "2016-01-01") -> dict:
    """Download all FRED macro series. Returns {series_id: rows_saved}."""
    api_key = os.environ.get("FRED_API_KEY", "")
    if not api_key:
        logger.warning("FRED_API_KEY not set, skipping FRED download")
        logger.info("  Set FRED_API_KEY env var or add to .env file")
        logger.info("  Get free key at: https://fred.stlouisfed.org/docs/api/api_key.html")
        return {}

    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    results = {}
    end_date = datetime.now().strftime("%Y-%m-%d")

    for category, series_list in FRED_SERIES.items():
        for series_id in series_list:
            url = f"{FRED_URL}?series_id={series_id}&api_key={api_key}&file_type=json&observation_start={start_date}&observation_end={end_date}"
            text = http_get(url)
            if not text:
                results[series_id] = 0
                continue

            try:
                data = json.loads(text)
                observations = data.get("observations", [])
                rows = []
                for obs in observations:
                    val = obs.get("value", ".")
                    if val == ".":
                        continue
                    rows.append({"date": obs["date"], "value": float(val)})

                if rows:
                    out_path = MACRO_DIR / f"{series_id}.csv"
                    pd.DataFrame(rows).to_csv(out_path, index=False)
                    results[series_id] = len(rows)
                else:
                    results[series_id] = 0
            except Exception as e:
                logger.warning("  FRED %s error: %s", series_id, e)
                results[series_id] = 0

            time.sleep(0.5)

    ok = sum(1 for v in results.values() if v > 0)
    logger.info("FRED: %d/%d series downloaded", ok, len(results))
    return results


# ── Source: Stooq Dump (offline) ──────────────────────────────────────

STOOQ_DUMP_MAP = {
    "EURUSD": "currencies/major/eurusd.txt",
    "GBPUSD": "currencies/major/gbpusd.txt",
    "USDJPY": "currencies/major/usdjpy.txt",
    "AUDUSD": "currencies/major/audusd.txt",
    "USDCAD": "currencies/major/usdcad.txt",
    "USDCHF": "currencies/major/usdchf.txt",
    "NZDUSD": "currencies/major/nzdusd.txt",
    "XAUUSD": "currencies/major/xauusd.txt",
    "XAGUSD": "currencies/major/xagusd.txt",
    "BTCUSD": "currencies/other/btcusd.txt",
    "BTC_CRYPTO": "cryptocurrencies/btc.v.txt",
    "ETH_CRYPTO": "cryptocurrencies/eth.v.txt",
    "US30": "indices/^dji.txt",
    "NAS100": "indices/^ndx.txt",
}


def parse_stooq_txt(filepath: Path) -> pd.DataFrame:
    """Parse Stooq bulk TXT format."""
    rows = []
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) < 8:
                continue
            try:
                dt = datetime.strptime(row[2], "%Y%m%d").replace(tzinfo=UTC)
                rows.append({
                    "time": dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "open": float(row[4]), "high": float(row[5]),
                    "low": float(row[6]), "close": float(row[7]),
                    "volume": float(row[8]) if len(row) > 8 and row[8] else 0.0,
                })
            except (ValueError, IndexError):
                continue
    if not rows:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.DataFrame(rows)
    df.drop_duplicates(subset=["time"], keep="first", inplace=True)
    df.sort_values("time", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def ingest_stooq_dump(dump_dir: Path, symbols: list[str] | None = None) -> dict:
    """Ingest Stooq bulk dump directory."""
    if not dump_dir.exists():
        logger.error("Dump dir not found: %s", dump_dir)
        return {}

    world_dir = dump_dir / "data" / "daily" / "world"
    if not world_dir.exists():
        logger.error("No data/daily/world/ in dump dir")
        return {}

    targets = symbols or list(STOOQ_DUMP_MAP.keys())
    results = {}

    for symbol in targets:
        rel_path = STOOQ_DUMP_MAP.get(symbol)
        if not rel_path:
            # Try crypto fallback
            if symbol == "ETHUSD":
                rel_path = "currencies/other/ethusd.txt"
                if not (world_dir / rel_path).exists():
                    rel_path = "cryptocurrencies/eth.v.txt"
            elif symbol == "BTCUSD":
                rel_path = "currencies/other/btcusd.txt"
                if not (world_dir / rel_path).exists():
                    rel_path = "cryptocurrencies/btc.v.txt"
            else:
                continue

        filepath = world_dir / rel_path
        if not filepath.exists():
            logger.warning("  %s: not found at %s", symbol, rel_path)
            results[symbol] = 0
            continue

        df = parse_stooq_txt(filepath)
        if df.empty:
            results[symbol] = 0
            continue

        out_path = output_path(symbol, "D1")
        merged = merge_csv(df, out_path)
        merged.to_csv(out_path, index=False)
        results[symbol] = len(merged)
        logger.info("  %s: %d rows (%s to %s)", symbol, len(merged), merged["time"].min()[:10], merged["time"].max()[:10])

    ok = sum(1 for v in results.values() if v > 0)
    logger.info("Stooq dump: %d/%d symbols ingested", ok, len(results))
    return results


# ── Orchestrator ──────────────────────────────────────────────────────

def route_source(symbol: str, timeframe: str) -> str:
    """Determine which source to use for a symbol/timeframe combination."""
    if symbol in CRYPTO_SYMBOLS:
        if timeframe in INTRADAY_TFS:
            return "binance"
        return "yfinance"
    if symbol in FX_SYMBOLS:
        if timeframe in INTRADAY_TFS:
            return "stooq"
        return "yfinance"
    if timeframe in INTRADAY_TFS:
        return "stooq"
    return "yfinance"


def pull_symbol(symbol: str, timeframe: str, start: datetime, end: datetime, source: str | None = None) -> pd.DataFrame:
    """Pull data for one symbol+timeframe using the appropriate source."""
    src = source or route_source(symbol, timeframe)

    if src == "binance":
        return pull_binance(symbol, timeframe, start, end)
    elif src == "stooq":
        return pull_stooq(symbol, timeframe, start, end)
    elif src == "yfinance":
        return pull_yfinance(symbol)
    else:
        logger.warning("  Unknown source %s for %s/%s", src, symbol, timeframe)
        return pd.DataFrame(columns=COLUMNS)


def cmd_pull(args) -> int:
    """Pull OHLCV data from online sources."""
    logger.info("=" * 60)
    logger.info("Data Pipeline — Pull")
    logger.info("=" * 60)

    symbols = args.symbols or list(CRYPTO_SYMBOLS | FX_SYMBOLS)
    timeframes = args.timeframes or ["D1"]
    start = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=UTC) if args.start else datetime(2020, 1, 1, tzinfo=UTC)
    end = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=UTC) if args.end else datetime.now(UTC)
    source = args.source

    logger.info("  Symbols: %s", symbols)
    logger.info("  Timeframes: %s", timeframes)
    logger.info("  Range: %s to %s", start.date(), end.date())
    logger.info("  Source: %s", source or "auto")
    logger.info("=" * 60)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    results = []

    for symbol in symbols:
        for tf in timeframes:
            df = pull_symbol(symbol, tf, start, end, source)
            if df.empty:
                results.append((symbol, tf, 0, "no data"))
                continue

            out = output_path(symbol, tf)
            merged = merge_csv(df, out)
            merged.to_csv(out, index=False)
            results.append((symbol, tf, len(merged), "ok"))
            logger.info("  %s_%s: %d rows saved", symbol, tf, len(merged))

    # Summary
    ok = sum(1 for _, _, _, s in results if s == "ok")
    logger.info("\n" + "=" * 60)
    logger.info("Summary: %d/%d combinations saved", ok, len(results))
    for sym, tf, rows, status in results:
        logger.info("  %s_%s: %s (%d rows)", sym, tf, status, rows)
    logger.info("=" * 60)
    return 0


def cmd_status(args) -> int:
    """Show current data coverage."""
    logger.info("=" * 60)
    logger.info("Data Pipeline — Status")
    logger.info("=" * 60)

    symbols = args.symbols or sorted(CRYPTO_SYMBOLS | FX_SYMBOLS | INDEX_SYMBOLS)
    timeframes = args.timeframes or ["M1", "M5", "M15", "H1", "D1"]

    for sym in symbols:
        for tf in timeframes:
            path = output_path(sym, tf)
            if path.exists():
                try:
                    df = pd.read_csv(path, usecols=["time"], dtype={"time": str})
                    if not df.empty:
                        rows = len(df)
                        first = df["time"].min()[:10]
                        last = df["time"].max()[:10]
                        size_kb = path.stat().st_size / 1024
                        logger.info("  %s_%s: %6d rows | %s to %s | %5.0f KB", sym, tf, rows, first, last, size_kb)
                    else:
                        logger.info("  %s_%s: EMPTY", sym, tf)
                except Exception:
                    logger.info("  %s_%s: ERROR reading", sym, tf)
            # Don't print MISSING for every combo, only if --verbose

    logger.info("=" * 60)
    return 0


def cmd_ingest(args) -> int:
    """Ingest offline Stooq dump."""
    dump_dir = Path(args.dump_dir)
    symbols = args.symbols
    results = ingest_stooq_dump(dump_dir, symbols)
    return 0 if any(v > 0 for v in results.values()) else 1


def cmd_fred(args) -> int:
    """Pull FRED macro data."""
    results = pull_fred(args.start or "2016-01-01")
    return 0 if any(v > 0 for v in results.values()) else 1


def cmd_cot(args) -> int:
    """Pull COT (Commitments of Traders) data from cftc.gov."""
    try:
        from cot_reports import cot_year
    except ImportError:
        logger.error("cot_reports not installed: pip install cot-reports")
        return 1

    COT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = COT_DIR / "cot_legacy.csv"

    frames = []
    for yr in range(args.start_year, args.end_year + 1):
        try:
            df = cot_year(yr, "legacy_fut", store_txt=True, verbose=False)
            frames.append(df)
            logger.info(f"  COT {yr}: {len(df)} rows")
        except Exception as e:
            logger.warning(f"  COT {yr}: failed ({e})")

    if not frames:
        logger.error("No COT data downloaded")
        return 1

    combined = pd.concat(frames, ignore_index=True)
    combined.drop_duplicates(inplace=True)
    combined.sort_values(combined.columns[0], inplace=True)
    combined.to_csv(out_path, index=False)
    logger.info(f"COT saved: {len(combined)} rows -> {out_path}")
    return 0


# ── CLI ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Unified data pipeline for quant_os",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command")

    # pull
    p_pull = sub.add_parser("pull", help="Pull OHLCV data from online sources")
    p_pull.add_argument("--symbols", nargs="*", help="Symbols to pull")
    p_pull.add_argument("--timeframes", nargs="*", help="Timeframes (M1 M5 M15 H1 D1)")
    p_pull.add_argument("--start", default="2020-01-01", help="Start date YYYY-MM-DD")
    p_pull.add_argument("--end", default=None, help="End date YYYY-MM-DD (default: today)")
    p_pull.add_argument("--source", choices=["binance", "stooq", "yfinance"], help="Force specific source")
    p_pull.add_argument("--all", action="store_true", help="Pull all symbols and timeframes")

    # status
    p_status = sub.add_parser("status", help="Show data coverage")
    p_status.add_argument("--symbols", nargs="*", help="Symbols to check")
    p_status.add_argument("--timeframes", nargs="*", help="Timeframes to check")

    # ingest
    p_ingest = sub.add_parser("ingest", help="Ingest offline Stooq dump")
    p_ingest.add_argument("--dump-dir", required=True, help="Path to Stooq dump directory")
    p_ingest.add_argument("--symbols", nargs="*", help="Specific symbols")

    # fred
    p_fred = sub.add_parser("fred", help="Pull FRED macro data")
    p_fred.add_argument("--start", default="2016-01-01", help="Start date")

    # cot
    p_cot = sub.add_parser("cot", help="Pull COT (Commitments of Traders) data")
    p_cot.add_argument("--start-year", type=int, default=2020, help="Start year")
    p_cot.add_argument("--end-year", type=int, default=2026, help="End year")

    args = parser.parse_args()

    if args.command == "pull":
        if args.all:
            args.symbols = sorted(CRYPTO_SYMBOLS | FX_SYMBOLS)
            args.timeframes = ["M1", "M5", "M15", "H1", "D1"]
        return cmd_pull(args)
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "ingest":
        return cmd_ingest(args)
    elif args.command == "fred":
        return cmd_fred(args)
    elif args.command == "cot":
        return cmd_cot(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())

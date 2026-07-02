"""Ingest Stooq bulk data dump into quant_os data directory.

Usage:
    python scripts/ingest_stooq_dump.py --dump-dir "C:/Users/menum/Downloads/d_world_txt"
    python scripts/ingest_stooq_dump.py --dump-dir "C:/Users/menum/Downloads/d_world_txt" --symbols EURUSD XAUUSD BTCUSD ETHUSD
    python scripts/ingest_stooq_dump.py --dump-dir "C:/Users/menum/Downloads/d_world_txt" --all

Stooq format:
    <TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>,<OPENINT>

Output format (quant_os standard):
    time,open,high,low,close,volume
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from datetime import datetime, UTC
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ── Symbol mapping: quant_os name -> Stooq filename ─────────────────
SYMBOL_MAP = {
    # Currencies (major)
    "EURUSD": "currencies/major/eurusd.txt",
    "GBPUSD": "currencies/major/gbpusd.txt",
    "USDJPY": "currencies/major/usdjpy.txt",
    "AUDUSD": "currencies/major/audusd.txt",
    "USDCAD": "currencies/major/usdcad.txt",
    "USDCHF": "currencies/major/usdchf.txt",
    "NZDUSD": "currencies/major/nzdusd.txt",
    "XAUUSD": "currencies/major/xauusd.txt",
    "XAGUSD": "currencies/major/xagusd.txt",
    # Crypto (in currencies/other)
    "BTCUSD": "currencies/other/btcusd.txt",
    "ETHUSD": "currencies/other/ethusd.txt",
    # Crypto (in cryptocurrencies - fallback)
    "BTC_CRYPTO": "cryptocurrencies/btc.v.txt",
    "ETH_CRYPTO": "cryptocurrencies/eth.v.txt",
    # Indices
    "US30": "indices/^dji.txt",
    "NAS100": "indices/^ndx.txt",
    "SPX500": "indices/^spx.txt",
    "DAX40": "indices/^dax.txt",
    "FTSE100": "indices/^ftse.txt",
    "NK225": "indices/^nkx.txt",
    # Bonds (10-year yields)
    "US10Y": "bonds/10yusy.b.txt",
    "DE10Y": "bonds/10ydey.b.txt",
    "JP10Y": "bonds/10yjpy.b.txt",
    "UK10Y": "bonds/10ygby.b.txt",
}


def parse_stooq_file(filepath: str | Path) -> pd.DataFrame:
    """Parse a Stooq TXT file into a DataFrame with standard columns."""
    filepath = Path(filepath)
    if not filepath.exists():
        logger.warning("File not found: %s", filepath)
        return pd.DataFrame()

    rows = []
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            return pd.DataFrame()

        for row in reader:
            if len(row) < 8:
                continue
            try:
                ticker, per, date_str, time_str, open_, high, low, close = row[:8]
                vol = float(row[8]) if len(row) > 8 and row[8] else 0.0

                # Parse date
                dt = datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=UTC)
                if time_str and time_str != "000000":
                    dt = dt.replace(
                        hour=int(time_str[:2]),
                        minute=int(time_str[2:4]),
                        second=int(time_str[4:6]),
                    )

                rows.append({
                    "time": dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "open": float(open_),
                    "high": float(high),
                    "low": float(low),
                    "close": float(close),
                    "volume": vol,
                })
            except (ValueError, IndexError):
                continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df.drop_duplicates(subset=["time"], keep="first", inplace=True)
    df.sort_values("time", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def merge_with_existing(new_df: pd.DataFrame, existing_path: Path) -> pd.DataFrame:
    """Merge new data with existing CSV, deduplicate, sort."""
    if not existing_path.exists() or new_df.empty:
        return new_df

    try:
        existing = pd.read_csv(existing_path)
        if existing.empty:
            return new_df

        # Find overlap
        existing_max = existing["time"].max()
        new_min = new_df["time"].min()

        if new_min > existing_max:
            # No overlap, just concatenate
            combined = pd.concat([existing, new_df], ignore_index=True)
        else:
            # Overlap: prefer new data for overlapping timestamps
            combined = pd.concat([existing, new_df], ignore_index=True)
            combined.drop_duplicates(subset=["time"], keep="last", inplace=True)

        combined.sort_values("time", inplace=True)
        combined.reset_index(drop=True, inplace=True)
        return combined
    except Exception as e:
        logger.warning("Could not merge with %s: %s", existing_path, e)
        return new_df


def ingest_symbol(
    symbol: str,
    dump_dir: Path,
    output_dir: Path,
    stooq_path: str | None = None,
) -> dict:
    """Ingest one symbol from Stooq dump."""
    result = {"symbol": symbol, "rows": 0, "status": "skipped"}

    # Find the file
    if stooq_path:
        filepath = dump_dir / "data" / "daily" / "world" / stooq_path
    else:
        # Try to find automatically
        for subdir in ["currencies/major", "currencies/other", "cryptocurrencies", "indices", "bonds"]:
            for ext in [".txt", ""]:
                candidate = dump_dir / "data" / "daily" / "world" / subdir / f"{symbol.lower()}{ext}"
                if candidate.exists():
                    filepath = candidate
                    break
                # Try with .b.txt for bonds
                candidate = dump_dir / "data" / "daily" / "world" / subdir / f"{symbol.lower()}.b.txt"
                if candidate.exists():
                    filepath = candidate
                    break
            else:
                continue
            break
        else:
            logger.warning("  %s: not found in dump", symbol)
            return result

    if not filepath.exists():
        logger.warning("  %s: file not found at %s", symbol, filepath)
        return result

    # Parse
    df = parse_stooq_file(filepath)
    if df.empty:
        logger.warning("  %s: no data parsed", symbol)
        return result

    logger.info("  %s: parsed %d rows (%s to %s)", symbol, len(df), df["time"].min(), df["time"].max())

    # Merge with existing
    out_path = output_dir / f"{symbol}_D1.csv"
    merged = merge_with_existing(df, out_path)

    # Save
    merged.to_csv(out_path, index=False)
    logger.info("  %s: saved %d rows to %s", symbol, len(merged), out_path.name)

    result["rows"] = len(merged)
    result["status"] = "ok"
    result["range"] = f"{merged['time'].min()} to {merged['time'].max()}"
    return result


def ingest_all(
    dump_dir: Path,
    output_dir: Path,
    symbols: list[str] | None = None,
    include_indices: bool = False,
    include_bonds: bool = False,
) -> list[dict]:
    """Ingest all symbols from Stooq dump."""
    results = []

    if symbols is None:
        symbols = list(SYMBOL_MAP.keys())

    for symbol in symbols:
        stooq_path = SYMBOL_MAP.get(symbol)
        if stooq_path:
            result = ingest_symbol(symbol, dump_dir, output_dir, stooq_path)
        else:
            result = ingest_symbol(symbol, dump_dir, output_dir)
        results.append(result)

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest Stooq bulk data dump")
    parser.add_argument("--dump-dir", required=True, help="Path to Stooq dump directory")
    parser.add_argument("--symbols", nargs="*", help="Specific symbols to ingest")
    parser.add_argument("--all", action="store_true", help="Ingest all available symbols")
    parser.add_argument("--output", type=str, default=str(DATA_DIR), help="Output directory")
    args = parser.parse_args()

    dump_dir = Path(args.dump_dir)
    if not dump_dir.exists():
        logger.error("Dump directory not found: %s", dump_dir)
        return 1

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("Stooq Data Ingestion")
    logger.info("=" * 60)
    logger.info("  Dump dir: %s", dump_dir)
    logger.info("  Output dir: %s", output_dir)

    if args.all:
        symbols = list(SYMBOL_MAP.keys())
    elif args.symbols:
        symbols = args.symbols
    else:
        # Default: our 4 target symbols + key cross-asset
        symbols = ["EURUSD", "XAUUSD", "BTCUSD", "ETHUSD", "GBPUSD", "USDJPY", "US30", "NAS100"]

    logger.info("  Symbols: %s", symbols)
    logger.info("=" * 60)

    results = ingest_all(dump_dir, output_dir, symbols)

    # Summary
    ok = [r for r in results if r["status"] == "ok"]
    skipped = [r for r in results if r["status"] == "skipped"]

    logger.info("\n" + "=" * 60)
    logger.info("Summary")
    logger.info("=" * 60)
    for r in results:
        if r["status"] == "ok":
            logger.info("  ✅ %s: %d rows (%s)", r["symbol"], r["rows"], r.get("range", ""))
        else:
            logger.info("  ❌ %s: %s", r["symbol"], r["status"])

    logger.info("\n  Total: %d ok, %d skipped", len(ok), len(skipped))
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
TickVault Integration — Download tick data with resume and gap detection.

TickVault is a free tick data source that supports:
- Resume download (checkpoint-based)
- Gap detection (missing data identification)
- Multiple symbols (XAUUSD, XAGUSD, forex pairs)

This script provides a wrapper around TickVault CLI for integration
with the quant_os data pipeline.

Usage:
    python scripts/download_tickvault.py --symbols XAUUSD --start 2020-01-01 --end 2024-12-31
    python scripts/download_tickvault.py --symbols XAUUSD,XAGUSD --resume

Requirements:
    - tickvault Python package (pip install tickvault)
    - Or: TickVault CLI installed separately

Output: data/ticks/{symbol}/ directory with tick data files
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import date as Date, datetime, timedelta, UTC
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── Constants ──
DATA_DIR = PROJECT_ROOT / "data"
TICK_DIR = DATA_DIR / "ticks"
CHECKPOINT_FILE = ".tickvault_checkpoint.json"

# Supported symbols
SUPPORTED_SYMBOLS = [
    "XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY",
    "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
]


def check_tickvault_available() -> bool:
    """Check if TickVault is available."""
    try:
        result = subprocess.run(
            ["tickvault", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def download_tickvault_cli(
    symbol: str,
    start: Date,
    end: Date,
    output_dir: Path,
    resume: bool = True,
) -> int:
    """Download tick data using TickVault CLI.

    Returns number of ticks downloaded.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "tickvault",
        "download",
        "--symbol", symbol,
        "--start", start.isoformat(),
        "--end", end.isoformat(),
        "--output", str(output_dir),
        "--format", "csv",
    ]

    if resume:
        cmd.append("--resume")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour timeout
        )

        if result.returncode != 0:
            print(f"  TickVault error: {result.stderr}")
            return 0

        # Parse output for tick count
        for line in result.stdout.split("\n"):
            if "ticks" in line.lower() or "rows" in line.lower():
                # Try to extract number
                import re
                match = re.search(r'(\d+)', line)
                if match:
                    return int(match.group(1))

        return 0

    except subprocess.TimeoutExpired:
        print("  TickVault download timed out")
        return 0
    except FileNotFoundError:
        print("  TickVault CLI not found")
        return 0


def download_dukascopy_fallback(
    symbol: str,
    start: Date,
    end: Date,
    output_dir: Path,
) -> int:
    """Fallback: Use existing Dukascopy downloader."""
    script_path = PROJECT_ROOT / "scripts" / "download_duka.py"
    if not script_path.exists():
        print("  Dukascopy downloader not found")
        return 0

    cmd = [
        sys.executable,
        str(script_path),
        "--symbols", symbol,
        "--start", start.isoformat(),
        "--end", end.isoformat(),
        "--output", str(output_dir),
        "--workers", "4",
        "--resume",
        "--fallback", "stooq",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,
        )

        if result.returncode != 0:
            print(f"  Dukascopy error: {result.stderr}")
            return 0

        # Parse output for tick count
        for line in result.stdout.split("\n"):
            if "ticks" in line.lower():
                import re
                match = re.search(r'(\d[\d,]+)', line)
                if match:
                    return int(match.group(1).replace(",", ""))

        return 0

    except subprocess.TimeoutExpired:
        print("  Dukascopy download timed out")
        return 0


def load_checkpoint(output_dir: Path) -> dict:
    """Load download checkpoint."""
    path = output_dir / CHECKPOINT_FILE
    if path.exists():
        with open(path, "r") as f:
            return json.load(f)
    return {"completed": [], "version": 1}


def save_checkpoint(output_dir: Path, checkpoint: dict):
    """Save download checkpoint."""
    path = output_dir / CHECKPOINT_FILE
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(checkpoint, f, indent=2, sort_keys=True)
    tmp.replace(path)


def main():
    parser = argparse.ArgumentParser(description="Download tick data via TickVault")
    parser.add_argument("--symbols", type=str, default="XAUUSD",
                        help="Comma-separated symbols (default: XAUUSD)")
    parser.add_argument("--start", type=str, default="2020-01-01",
                        help="Start date YYYY-MM-DD (default: 2020-01-01)")
    parser.add_argument("--end", type=str, default=None,
                        help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--resume", action="store_true", default=True,
                        help="Resume from checkpoint (default: True)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output directory (default: data/ticks)")
    parser.add_argument("--source", type=str, default="auto",
                        choices=["auto", "tickvault", "dukascopy"],
                        help="Data source (default: auto)")
    args = parser.parse_args()

    start_date = Date.fromisoformat(args.start)
    end_date = Date.fromisoformat(args.end) if args.end else Date.today()
    output_dir = Path(args.output) if args.output else TICK_DIR

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    print("=" * 60)
    print("Tick Data Download")
    print("=" * 60)
    print(f"Symbols: {symbols}")
    print(f"Range: {start_date} → {end_date}")
    print(f"Output: {output_dir}")
    print()

    # Check TickVault availability
    tickvault_ok = False
    if args.source in ("auto", "tickvault"):
        print("Checking TickVault...", end=" ", flush=True)
        tickvault_ok = check_tickvault_available()
        print("OK" if tickvault_ok else "NOT FOUND")

    total_ticks = 0
    errors = 0

    for symbol in symbols:
        print(f"\n{'='*40}")
        print(f"Processing {symbol}...")
        print(f"{'='*40}")

        symbol_dir = output_dir / symbol
        checkpoint = load_checkpoint(symbol_dir)

        # Try TickVault first
        if tickvault_ok and args.source in ("auto", "tickvault"):
            print("  Using TickVault...", end=" ", flush=True)
            ticks = download_tickvault_cli(
                symbol, start_date, end_date, symbol_dir, args.resume
            )
            if ticks > 0:
                print(f"OK ({ticks:,} ticks)")
                total_ticks += ticks
                continue
            else:
                print("FAILED")

        # Fallback to Dukascopy
        if args.source in ("auto", "dukascopy"):
            print("  Using Dukascopy fallback...", end=" ", flush=True)
            ticks = download_dukascopy_fallback(
                symbol, start_date, end_date, symbol_dir
            )
            if ticks > 0:
                print(f"OK ({ticks:,} ticks)")
                total_ticks += ticks
            else:
                print("FAILED")
                errors += 1

    # Summary
    print("\n" + "=" * 60)
    print("Download Complete")
    print("=" * 60)
    print(f"Total ticks: {total_ticks:,}")
    print(f"Errors: {errors}")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()

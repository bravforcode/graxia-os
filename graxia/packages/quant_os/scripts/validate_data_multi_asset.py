#!/usr/bin/env python3
"""
Multi-Asset Data Validator for Quant OS
=========================================
Batch-validates all CSV files in data/ for the target symbols:
  - Missing values
  - OHLC integrity (high >= low, open/close within range)
  - Volume > 0
  - D1 data gaps > 5 business days

Outputs a JSON report to reports/data_validation.json.

Usage:
    python scripts/validate_data_multi_asset.py
    python scripts/validate_data_multi_asset.py --symbols BTCUSD,ETHUSD,XAUUSD,EURUSD
    python scripts/validate_data_multi_asset.py --timeframes D1,H1,M15
    python scripts/validate_data_multi_asset.py --gap-threshold 10
"""

import argparse
import csv
import json
import os
import sys
from datetime import UTC, datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DEFAULT_OUTPUT = os.path.join(PROJECT_ROOT, "reports", "data_validation.json")

# Target symbols for multi-asset redesign
DEFAULT_SYMBOLS = ["XAUUSD", "EURUSD", "BTCUSD", "ETHUSD"]
DEFAULT_TIMEFRAMES = ["D1", "H4", "H1", "M15", "M5", "M1", "W1", "MN1"]

# Business day gap threshold (for D1)
DEFAULT_GAP_THRESHOLD_DAYS = 5


# ---------------------------------------------------------------------------
# CSV Reader
# ---------------------------------------------------------------------------
def read_csv(filepath: str) -> list[dict]:
    """Read CSV and return list of row dicts."""
    rows = []
    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Timestamp Parser
# ---------------------------------------------------------------------------
def parse_ts(val: str) -> datetime | None:
    """Parse various timestamp formats to datetime."""
    if not val or val.strip() == "":
        return None
    for fmt in [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d",
    ]:
        try:
            return datetime.strptime(val.strip(), fmt)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------
def check_missing_values(rows: list[dict]) -> dict:
    """Check for missing/empty values in all columns."""
    if not rows:
        return {"status": "FAIL", "missing_counts": {}, "total_rows": 0}

    columns = list(rows[0].keys())
    missing_counts = {}
    for col in columns:
        count = sum(1 for row in rows if row.get(col) is None or str(row.get(col, "")).strip() == "")
        if count > 0:
            missing_counts[col] = count

    total = len(rows)
    total_missing = sum(missing_counts.values())
    pct = total_missing / (total * len(columns)) if total > 0 else 0

    return {
        "status": "PASS" if pct < 0.01 else ("WARN" if pct < 0.05 else "FAIL"),
        "total_rows": total,
        "total_missing_cells": total_missing,
        "missing_pct": round(pct, 6),
        "missing_counts": missing_counts,
    }


def check_ohlc_integrity(rows: list[dict]) -> dict:
    """Check OHLC integrity: high >= low, open/close within [low, high]."""
    violations = []
    samples = []

    for i, row in enumerate(rows):
        try:
            o = float(row.get("open", 0))
            h = float(row.get("high", 0))
            l = float(row.get("low", 0))
            c = float(row.get("close", 0))
        except (ValueError, TypeError):
            continue

        errors = []
        if h < l:
            errors.append(f"high({h}) < low({l})")
        if o < l:
            errors.append(f"open({o}) < low({l})")
        if o > h:
            errors.append(f"open({o}) > high({h})")
        if c < l:
            errors.append(f"close({c}) < low({l})")
        if c > h:
            errors.append(f"close({c}) > high({h})")

        if errors:
            violations.append(i)
            if len(samples) < 5:
                ts = row.get("time") or row.get("timestamp", f"row_{i}")
                samples.append({"row": i, "timestamp": str(ts), "errors": errors})

    total = len(rows)
    pct = len(violations) / total if total > 0 else 0

    return {
        "status": "PASS" if pct < 0.001 else ("WARN" if pct < 0.01 else "FAIL"),
        "total_rows": total,
        "violations": len(violations),
        "violation_pct": round(pct, 6),
        "samples": samples,
    }


def check_volume(rows: list[dict]) -> dict:
    """Check that volume > 0 for all rows."""
    zero_vol_rows = []
    neg_vol_rows = []

    for i, row in enumerate(rows):
        try:
            vol = float(row.get("volume", 0))
        except (ValueError, TypeError):
            continue

        if vol <= 0:
            zero_vol_rows.append(i)
            if vol < 0:
                neg_vol_rows.append(i)

    total = len(rows)
    zero_pct = len(zero_vol_rows) / total if total > 0 else 0
    neg_pct = len(neg_vol_rows) / total if total > 0 else 0

    # For crypto, volume=0 is common in early data — warn only
    status = "PASS"
    if neg_pct > 0:
        status = "FAIL"
    elif zero_pct > 0.5:
        status = "WARN"

    return {
        "status": status,
        "total_rows": total,
        "zero_volume_rows": len(zero_vol_rows),
        "zero_volume_pct": round(zero_pct, 4),
        "negative_volume_rows": len(neg_vol_rows),
        "negative_volume_pct": round(neg_pct, 4),
    }


def check_d1_gaps(rows: list[dict], gap_threshold_days: int = 5) -> dict:
    """Check D1 data for gaps > gap_threshold_days business days."""
    timestamps = []
    for row in rows:
        ts_str = row.get("time") or row.get("timestamp", "")
        ts = parse_ts(ts_str)
        if ts:
            timestamps.append(ts)

    if len(timestamps) < 2:
        return {
            "status": "PASS",
            "reason": "Insufficient timestamps for gap detection",
        }

    timestamps.sort()
    gaps = []
    for i in range(1, len(timestamps)):
        delta = timestamps[i] - timestamps[i - 1]
        delta_days = delta.total_seconds() / 86400
        if delta_days > gap_threshold_days:
            gaps.append(
                {
                    "from": timestamps[i - 1].strftime("%Y-%m-%d"),
                    "to": timestamps[i].strftime("%Y-%m-%d"),
                    "gap_days": round(delta_days, 1),
                }
            )

    status = "PASS" if len(gaps) == 0 else "FAIL"
    return {
        "status": status,
        "gap_threshold_days": gap_threshold_days,
        "gaps_found": len(gaps),
        "gaps": gaps[:20],  # cap at 20 samples
    }


def check_price_range(rows: list[dict], symbol: str) -> dict:
    """Check price ranges are plausible for the symbol."""
    # Expected ranges (approximate)
    ranges = {
        "XAUUSD": (500, 10000),
        "EURUSD": (0.5, 2.0),
        "BTCUSD": (0.01, 500000),
        "ETHUSD": (0.01, 50000),
    }

    if symbol not in ranges:
        return {"status": "SKIP", "reason": f"No range defined for {symbol}"}

    low_bound, high_bound = ranges[symbol]
    violations = []

    for i, row in enumerate(rows):
        for col in ["open", "high", "low", "close"]:
            try:
                val = float(row.get(col, 0))
            except (ValueError, TypeError):
                continue
            if val < low_bound or val > high_bound:
                ts = row.get("time") or row.get("timestamp", f"row_{i}")
                violations.append(
                    {
                        "row": i,
                        "timestamp": str(ts),
                        "column": col,
                        "value": val,
                    }
                )
                if len(violations) >= 5:
                    break
        if len(violations) >= 5:
            break

    total = len(rows)
    status = "PASS" if len(violations) == 0 else "WARN"
    return {
        "status": status,
        "expected_range": [low_bound, high_bound],
        "violations": len(violations),
        "samples": violations,
    }


# ---------------------------------------------------------------------------
# File Validator
# ---------------------------------------------------------------------------
def validate_file(filepath: str, symbol: str, timeframe: str, gap_threshold: int) -> dict:
    """Run all checks on a single CSV file."""
    filename = os.path.basename(filepath)
    result = {
        "file": filename,
        "symbol": symbol,
        "timeframe": timeframe,
        "path": os.path.abspath(filepath),
    }

    try:
        rows = read_csv(filepath)
    except Exception as e:
        result["status"] = "ERROR"
        result["error"] = str(e)
        return result

    result["total_rows"] = len(rows)

    if not rows:
        result["status"] = "FAIL"
        result["error"] = "Empty file"
        return result

    # Run checks
    checks = {}
    checks["missing_values"] = check_missing_values(rows)
    checks["ohlc_integrity"] = check_ohlc_integrity(rows)
    checks["volume"] = check_volume(rows)
    checks["price_range"] = check_price_range(rows, symbol)

    # D1 gap check only for D1 timeframe
    if timeframe == "D1":
        checks["d1_gaps"] = check_d1_gaps(rows, gap_threshold)

    result["checks"] = checks

    # Overall status
    statuses = [c["status"] for c in checks.values() if c.get("status")]
    if "FAIL" in statuses:
        result["status"] = "FAIL"
    elif "WARN" in statuses:
        result["status"] = "WARN"
    else:
        result["status"] = "PASS"

    return result


# ---------------------------------------------------------------------------
# Batch Validator
# ---------------------------------------------------------------------------
def find_csv_files(data_dir: str, symbol: str, timeframe: str) -> list[str]:
    """Find CSV files matching symbol and timeframe pattern."""
    patterns = [
        f"{symbol}_{timeframe}.csv",
    ]
    found = []
    for pat in patterns:
        path = os.path.join(data_dir, pat)
        if os.path.exists(path):
            found.append(path)
    return found


def run_validation(
    symbols: list[str],
    timeframes: list[str],
    gap_threshold: int,
    output_path: str,
) -> dict:
    """Run batch validation and return report."""
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = {
        "report_type": "data_validation_multi_asset",
        "generated_at_utc": ts,
        "data_dir": os.path.abspath(DATA_DIR),
        "symbols_validated": symbols,
        "timeframes_validated": timeframes,
        "gap_threshold_days": gap_threshold,
        "files": {},
        "summary": {},
    }

    total_files = 0
    total_pass = 0
    total_warn = 0
    total_fail = 0
    total_error = 0

    for symbol in symbols:
        for tf in timeframes:
            files = find_csv_files(DATA_DIR, symbol, tf)
            for filepath in files:
                total_files += 1
                result = validate_file(filepath, symbol, tf, gap_threshold)
                key = f"{symbol}_{tf}"
                report["files"][key] = result

                status = result.get("status", "ERROR")
                if status == "PASS":
                    total_pass += 1
                elif status == "WARN":
                    total_warn += 1
                elif status == "FAIL":
                    total_fail += 1
                else:
                    total_error += 1

    report["summary"] = {
        "total_files": total_files,
        "pass": total_pass,
        "warn": total_warn,
        "fail": total_fail,
        "error": total_error,
        "overall": "PASS" if total_fail == 0 and total_error == 0 else "FAIL",
    }

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-Asset Data Validator — batch CSV validation")
    parser.add_argument(
        "--symbols",
        "-s",
        default=",".join(DEFAULT_SYMBOLS),
        help=f"Comma-separated symbols (default: {','.join(DEFAULT_SYMBOLS)})",
    )
    parser.add_argument(
        "--timeframes",
        "-t",
        default=",".join(DEFAULT_TIMEFRAMES),
        help=f"Comma-separated timeframes (default: {','.join(DEFAULT_TIMEFRAMES)})",
    )
    parser.add_argument(
        "--gap-threshold",
        "-g",
        type=int,
        default=DEFAULT_GAP_THRESHOLD_DAYS,
        help=f"D1 gap threshold in days (default: {DEFAULT_GAP_THRESHOLD_DAYS})",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=DEFAULT_OUTPUT,
        help=f"Output JSON path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    timeframes = [t.strip().upper() for t in args.timeframes.split(",") if t.strip()]

    if not symbols:
        print("ERROR: No symbols specified")
        sys.exit(1)

    # Ensure output dir
    out_dir = os.path.dirname(args.output)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    print(f"Multi-Asset Data Validation — {len(symbols)} symbols, {len(timeframes)} timeframes")
    print("=" * 60)

    report = run_validation(symbols, timeframes, args.gap_threshold, args.output)

    # Print summary
    for key, data in report["files"].items():
        status = data.get("status", "ERROR")
        rows = data.get("total_rows", "?")
        icon = {"PASS": "OK", "WARN": "WARN", "FAIL": "FAIL", "ERROR": "ERR"}.get(status, "?")
        print(f"  [{icon}] {key:20s}  rows={rows:>8}", end="")
        if status in ("FAIL", "ERROR"):
            # Show failing checks
            checks = data.get("checks", {})
            fails = [k for k, v in checks.items() if v.get("status") == "FAIL"]
            if fails:
                print(f"  FAIL: {', '.join(fails)}", end="")
        print()

    print(f"\n{'=' * 60}")
    s = report["summary"]
    print(
        f"Overall: {s['overall']}  |  Files: {s['total_files']}  "
        f"Pass: {s['pass']}  Warn: {s['warn']}  Fail: {s['fail']}  Error: {s['error']}"
    )

    # Write JSON
    with open(args.output, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\nReport written to: {args.output}")
    sys.exit(0 if s["overall"] == "PASS" else 1)


if __name__ == "__main__":
    main()

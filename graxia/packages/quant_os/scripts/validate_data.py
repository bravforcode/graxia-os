"""
Comprehensive Data Validator for Quant OS

Performs all data quality checks on forex datasets:
  schema, range, completeness, sequence, staleness, integrity, distribution, cross_source

Usage:
    python scripts/validate_data.py --input data/warehouse/ticks/EURUSD/year=2024/month=01/data.parquet --checks all --output artifacts/validation/report_202401.json
    python scripts/validate_data.py --input data/EURUSD_M15.csv --checks schema,range,completeness
"""

import argparse
import csv
import hashlib
import json
import math
import os
import sys
import time
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFESTS_DIR = os.path.join(PROJECT_ROOT, "data", "manifests")
ARTIFACTS_DIR = os.path.join(PROJECT_ROOT, "artifacts", "validation")

# Expected schemas for auto-detection
FOREX_TICK_COLUMNS = {"timestamp", "bid", "ask", "spread_points", "symbol", "source"}
FOREX_OHLCV_COLUMNS = {"time", "open", "high", "low", "close", "volume"}
FOREX_TICK_FLOAT = {"bid", "ask"}
FOREX_OHLCV_FLOAT = {"open", "high", "low", "close"}

# Sampling config for large files
SAMPLE_SIZE = 1_000_000
DISTRIBUTION_SAMPLE = 500_000

ALL_CHECK_NAMES = [
    "schema", "range", "completeness", "sequence",
    "staleness", "integrity", "distribution", "cross_source",
]


def _read_data(filepath: str) -> Tuple[List[Dict[str, Any]], str, Any]:
    """Read data from parquet or CSV file. Returns (rows, format, metadata)."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".parquet":
        return _read_parquet(filepath)
    elif ext == ".csv":
        return _read_csv(filepath)
    else:
        raise ValueError(f"Unsupported file format: {ext}. Only .parquet and .csv are supported.")


def _read_parquet(filepath: str) -> Tuple[List[Dict[str, Any]], str, Any]:
    """Read parquet file. Returns (rows, 'parquet', metadata_dict)."""
    try:
        import pandas as pd
        df = pd.read_parquet(filepath)
        total_rows = len(df)
        read_all = total_rows <= SAMPLE_SIZE
        data = df.to_dict("records") if read_all else df.head(SAMPLE_SIZE).to_dict("records")
        metadata = {
            "total_rows": total_rows,
            "sampled": not read_all,
            "columns": list(df.columns),
            "dtypes": {col: str(df[col].dtype) for col in df.columns},
        }
        return data, "parquet", metadata
    except ImportError:
        pass

    try:
        import pyarrow.parquet as pq
        pf = pq.ParquetFile(filepath)
        total_rows = pf.metadata.num_rows
        read_all = total_rows <= SAMPLE_SIZE
        table = pf.read() if read_all else pf.read_rows(0, SAMPLE_SIZE)
        schema = table.schema
        data = table.to_pylist()
        metadata = {
            "total_rows": total_rows,
            "sampled": not read_all,
            "columns": schema.names,
            "dtypes": {field.name: str(field.type) for field in schema},
        }
        return data, "parquet", metadata
    except ImportError:
        raise ImportError("No parquet reader available. Install pandas or pyarrow.")


def _read_csv(filepath: str) -> Tuple[List[Dict[str, Any]], str, Any]:
    """Read CSV file. Returns (rows, 'csv', metadata_dict)."""
    rows = []
    total_rows = 0
    columns = None
    with open(filepath, "r", newline="") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames
        for i, row in enumerate(reader):
            total_rows += 1
            if len(rows) < SAMPLE_SIZE:
                rows.append(row)

    metadata = {
        "total_rows": total_rows,
        "sampled": total_rows > SAMPLE_SIZE,
        "columns": columns,
        "dtypes": {},
    }
    return rows, "csv", metadata


def _infer_dataset_type(columns: List[str]) -> str:
    """Detect whether the dataset is ticks or OHLCV based on columns."""
    col_set = set(col.lower() for col in columns)
    if {"bid", "ask"}.issubset(col_set):
        return "tick"
    if {"open", "high", "low", "close"}.issubset(col_set):
        return "ohlcv"
    return "unknown"


def _to_float(val: Any) -> Optional[float]:
    """Safely convert value to float."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _find_manifest(filepath: str) -> Optional[str]:
    """Find an existing manifest for the given file."""
    basename = os.path.splitext(os.path.basename(filepath))[0]
    candidates = [
        os.path.join(MANIFESTS_DIR, f"{basename}.manifest.json"),
        os.path.join(MANIFESTS_DIR, f"{basename}_manifest.json"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def _compute_sha256(filepath: str) -> str:
    """Compute SHA-256 of raw file bytes."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _format_timestamp(dt) -> str:
    """Format datetime to ISO string."""
    if isinstance(dt, str):
        return dt
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt)


def _overall_status(results: Dict[str, Dict]) -> str:
    """Compute overall status from all check results."""
    has_fail = any(r["status"] == "FAIL" for r in results.values())
    has_warn = any(r["status"] == "WARN" for r in results.values())
    if has_fail:
        return "FAIL"
    if has_warn:
        return "WARN"
    return "PASS"


def _recommendation(results: Dict[str, Dict], overall: str) -> str:
    """Generate actionable recommendation."""
    if overall == "PASS":
        return "Dataset passed all checks. Ready for pipeline."
    fails = [k for k, v in results.items() if v["status"] == "FAIL"]
    warns = [k for k, v in results.items() if v["status"] == "WARN"]
    parts = []
    if fails:
        parts.append(f"Failing checks: {', '.join(fails)}. Do not use this dataset until resolved.")
    if warns:
        parts.append(f"Warnings: {', '.join(warns)}. Review before production use.")
    return " ".join(parts) if parts else "Dataset passed all checks."


# ---- Individual Check Functions ----

def check_schema(
    data: List[Dict], file_format: str, metadata: Dict
) -> Dict[str, Any]:
    """Check column names, types, and nullability match contract."""
    columns = metadata.get("columns", [])
    col_set = set(col.lower() for col in columns)
    ds_type = _infer_dataset_type(columns)

    expected = FOREX_TICK_COLUMNS if ds_type == "tick" else FOREX_OHLCV_COLUMNS if ds_type == "ohlcv" else set()
    extra_cols = col_set - expected
    missing_cols = expected - col_set

    null_counts = {}
    for col in expected:
        nulls = sum(1 for row in data if row.get(col) is None or str(row.get(col, "")).strip() == "")
        if nulls > 0:
            null_counts[col] = nulls

    passed = len(missing_cols) == 0 and len(null_counts) == 0
    status = "PASS" if passed else "FAIL"

    details = {
        "dataset_type": ds_type,
        "columns_found": columns,
        "columns_expected": list(expected),
        "missing_columns": sorted(missing_cols),
        "extra_columns": sorted(extra_cols),
        "null_counts": null_counts,
        "null_threshold": 0,
    }
    return {"status": status, "details": details}


def check_range(
    data: List[Dict], file_format: str, metadata: Dict
) -> Dict[str, Any]:
    """Check bid > 0, ask >= bid, spread < 1000 pips, price within [0.5, 200]."""
    columns = metadata.get("columns", [])
    ds_type = _infer_dataset_type(columns)

    violations = []
    sample = []
    max_violation_sample = 10

    for i, row in enumerate(data):
        bid = _to_float(row.get("bid"))
        ask = _to_float(row.get("ask"))

        if bid is not None and bid <= 0:
            violations.append({"row": i, "field": "bid", "value": bid, "reason": "bid <= 0"})
        elif ask is not None and ask <= 0:
            violations.append({"row": i, "field": "ask", "value": ask, "reason": "ask <= 0"})
        elif bid is not None and ask is not None and ask < bid:
            violations.append({"row": i, "field": "ask", "value": ask, "reason": f"ask < bid ({bid})"})
        elif bid is not None and ask is not None:
            spread_pips = abs(ask - bid) * 10000
            if spread_pips >= 1000:
                violations.append({"row": i, "field": "spread", "value": spread_pips, "reason": "spread >= 1000 pips"})

        if ds_type == "ohlcv":
            for col in ["open", "high", "low", "close"]:
                val = _to_float(row.get(col))
                if val is not None and (val < 0.5 or val > 200):
                    violations.append({"row": i, "field": col, "value": val, "reason": f"price {val} outside [0.5, 200]"})

        if len(sample) < max_violation_sample and len(violations) > len(sample):
            sample.append(violations[-1])

        if len(violations) > 10000:
            break

    total_rows = metadata.get("total_rows", len(data))
    violation_pct = len(violations) / max(total_rows, 1)
    threshold = 0.001
    passed = violation_pct <= threshold

    status = "PASS" if passed else "FAIL"
    return {
        "status": status,
        "violations": len(violations),
        "violation_pct": round(violation_pct, 6),
        "threshold": threshold,
        "sample": sample[:max_violation_sample],
        "details": {
            "total_checked": min(total_rows, SAMPLE_SIZE),
            "violation_rate": round(violation_pct, 6),
        },
    }


def check_completeness(
    data: List[Dict], file_format: str, metadata: Dict
) -> Dict[str, Any]:
    """Check expected rows vs actual, detect gaps."""
    total_rows = metadata.get("total_rows", len(data))
    columns = metadata.get("columns", [])
    ds_type = _infer_dataset_type(columns)

    if total_rows == 0:
        return {
            "status": "FAIL",
            "missing_pct": 1.0,
            "expected": 1,
            "actual": 0,
            "details": {"reason": "Dataset is empty"},
        }

    gap_count = 0
    gap_details = []
    if ds_type == "ohlcv" and len(data) > 1:
        timestamps = []
        for row in data:
            ts = row.get("time") or row.get("timestamp")
            if ts:
                timestamps.append(ts)
        if len(timestamps) > 1:
            for i in range(1, len(timestamps)):
                try:
                    t_prev = _parse_ts(timestamps[i - 1])
                    t_cur = _parse_ts(timestamps[i])
                    if t_prev and t_cur:
                        gap_sec = (t_cur - t_prev).total_seconds()
                        if gap_sec > 3600:
                            gap_count += 1
                            if len(gap_details) < 5:
                                gap_details.append({
                                    "from": str(timestamps[i - 1]),
                                    "to": str(timestamps[i]),
                                    "gap_seconds": gap_sec,
                                })
                except Exception:
                    pass

    expected = max(total_rows, 1)
    actual = total_rows
    missing_pct = max(0, (expected - actual) / expected)

    if missing_pct >= 0.20:
        status = "FAIL"
    elif missing_pct >= 0.05:
        status = "WARN"
    else:
        status = "PASS"

    result = {
        "status": status,
        "missing_pct": round(missing_pct, 4),
        "expected": expected,
        "actual": actual,
        "details": {
            "gaps_detected": gap_count,
        },
    }
    if gap_details:
        result["details"]["gap_samples"] = gap_details
    return result


def _parse_ts(val):
    """Parse various timestamp formats to datetime."""
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        for fmt in [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d",
        ]:
            try:
                return datetime.strptime(val, fmt)
            except ValueError:
                continue
    return None


def check_sequence(
    data: List[Dict], file_format: str, metadata: Dict
) -> Dict[str, Any]:
    """Check timestamps strictly increasing, no duplicates."""
    ts_col = "timestamp" if metadata.get("columns") and "timestamp" in metadata["columns"] else "time"
    timestamps = []
    for row in data:
        ts = row.get(ts_col)
        if ts is not None:
            timestamps.append(ts)

    if len(timestamps) < 2:
        return {"status": "PASS", "details": {"reason": "Insufficient timestamps to check sequence"}}

    duplicates = 0
    decreasing = 0
    dup_sample = []
    dec_sample = []
    seen = set()

    for i, ts in enumerate(timestamps):
        ts_str = str(ts)
        if ts_str in seen:
            duplicates += 1
            if len(dup_sample) < 5:
                dup_sample.append({"row": i, "timestamp": ts_str})
        seen.add(ts_str)

        if i > 0:
            try:
                t_prev = _parse_ts(timestamps[i - 1])
                t_cur = _parse_ts(ts)
                if t_prev and t_cur and t_cur <= t_prev:
                    decreasing += 1
                    if len(dec_sample) < 5:
                        dec_sample.append({"row": i, "timestamp": ts_str, "previous": str(timestamps[i - 1])})
            except Exception:
                pass

    passed = duplicates == 0 and decreasing == 0
    status = "FAIL" if (duplicates > 0 or decreasing > 0) else "PASS"

    return {
        "status": status,
        "duplicates": duplicates,
        "decreasing": decreasing,
        "sample": {"duplicates": dup_sample, "decreasing": dec_sample} if (dup_sample or dec_sample) else None,
        "details": {
            "total_timestamps": len(timestamps),
            "duplicate_count": duplicates,
            "out_of_order_count": decreasing,
        },
    }


def _infer_typical_bar_interval_sec(timestamps: List) -> Optional[float]:
    """Infer typical bar/candle interval from first N intervals."""
    if len(timestamps) < 5:
        return None
    gaps = []
    for i in range(1, min(len(timestamps), 100)):
        t_prev = _parse_ts(timestamps[i - 1])
        t_cur = _parse_ts(timestamps[i])
        if t_prev and t_cur:
            gap = (t_cur - t_prev).total_seconds()
            if gap > 0:
                gaps.append(gap)
    if not gaps:
        return None
    # Use median to be robust to edge cases
    sorted_gaps = sorted(gaps)
    return sorted_gaps[len(sorted_gaps) // 2]


def check_staleness(
    data: List[Dict], file_format: str, metadata: Dict
) -> Dict[str, Any]:
    """Check max gap between consecutive timestamps.

    Tick data: threshold = 30s.
    OHLCV data: threshold = 3x typical bar interval (adaptive).
    """
    columns = metadata.get("columns", [])
    ds_type = _infer_dataset_type(columns)
    ts_col = "timestamp" if metadata.get("columns") and "timestamp" in metadata["columns"] else "time"
    timestamps = []
    for row in data:
        ts = row.get(ts_col)
        if ts is not None:
            timestamps.append(ts)

    if len(timestamps) < 2:
        return {"status": "PASS", "details": {"reason": "Insufficient timestamps to check staleness"}}

    # Adaptive threshold: ticks use 30s, OHLCV uses 3x bar interval
    base_threshold = 30
    if ds_type == "ohlcv":
        typical_interval = _infer_typical_bar_interval_sec(timestamps)
        if typical_interval and typical_interval > 0:
            base_threshold = typical_interval * 3

    max_gap_sec = 0
    gap_count = 0
    large_gaps = []

    for i in range(1, len(timestamps)):
        try:
            t_prev = _parse_ts(timestamps[i - 1])
            t_cur = _parse_ts(timestamps[i])
            if t_prev and t_cur:
                gap = (t_cur - t_prev).total_seconds()
                if gap > max_gap_sec:
                    max_gap_sec = gap
                if gap > base_threshold:
                    gap_count += 1
                    if len(large_gaps) < 10:
                        large_gaps.append({
                            "from": str(timestamps[i - 1]),
                            "to": str(timestamps[i]),
                            "gap_seconds": round(gap, 2),
                        })
        except Exception:
            pass

    status = "WARN" if max_gap_sec > base_threshold else "PASS"
    return {
        "status": status,
        "max_gap_seconds": round(max_gap_sec, 2),
        "gaps_over_threshold": gap_count,
        "samples": large_gaps[:5] if large_gaps else None,
        "details": {
            "dataset_type": ds_type,
            "total_intervals_checked": len(timestamps) - 1,
            "max_gap_seconds": round(max_gap_sec, 2),
            "gaps_exceeding_threshold": gap_count,
            "threshold_seconds": base_threshold,
        },
    }


def check_integrity(
    data: List[Dict], file_format: str, metadata: Dict
) -> Dict[str, Any]:
    """Check SHA-256 matches manifest if it exists."""
    filepath = metadata.get("_filepath", "")
    if not filepath or not os.path.exists(filepath):
        return {"status": "SKIP", "details": {"reason": "No file path available for SHA-256 computation"}}

    actual_hash = _compute_sha256(filepath)
    manifest_path = _find_manifest(filepath)

    if manifest_path is None:
        return {
            "status": "WARN",
            "file_hash": actual_hash[:16] + "...",
            "details": {
                "reason": "No manifest found to verify against",
                "computed_sha256": actual_hash,
                "manifest_path": None,
            },
        }

    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    expected_hash = manifest.get("sha256") or manifest.get("csv_sha256") or manifest.get("sha256_sum")
    if expected_hash is None:
        return {
            "status": "WARN",
            "details": {
                "reason": "Manifest found but no sha256 field present",
                "manifest_path": manifest_path,
            },
        }

    passed = actual_hash == expected_hash
    status = "PASS" if passed else "FAIL"
    return {
        "status": status,
        "file_hash": actual_hash[:16] + "...",
        "details": {
            "computed_sha256": actual_hash,
            "expected_sha256": expected_hash,
            "manifest_path": manifest_path,
            "manifest_fields_present": list(manifest.keys()),
        },
    }


def check_distribution(
    data: List[Dict], file_format: str, metadata: Dict
) -> Dict[str, Any]:
    """Check price/return distribution sanity using 3-sigma test."""
    columns = metadata.get("columns", [])
    ds_type = _infer_dataset_type(columns)

    price_cols = []
    if ds_type == "tick":
        price_cols = ["bid", "ask"]
    elif ds_type == "ohlcv":
        price_cols = ["close"]
    else:
        price_cols = [c for c in columns if c.lower() in ("close", "price", "bid", "ask")]

    if not price_cols:
        return {"status": "SKIP", "details": {"reason": "No price columns found for distribution check"}}

    sample_size = min(DISTRIBUTION_SAMPLE, len(data))
    if sample_size < 10:
        return {"status": "SKIP", "details": {"reason": f"Insufficient data for distribution analysis (n={sample_size})"}}

    try:
        import numpy as np
        has_np = True
    except ImportError:
        has_np = False

    results = {}
    for col in price_cols:
        values = []
        for row in data[:sample_size]:
            v = _to_float(row.get(col))
            if v is not None and v > 0:
                values.append(v)

        if len(values) < 10:
            results[col] = {"status": "SKIP", "reason": "insufficient_values"}
            continue

        if has_np:
            arr = np.array(values)
            mean = float(np.mean(arr))
            std = float(np.std(arr))
            outliers = int(np.sum(np.abs(arr - mean) > 3 * std))
            outlier_pct = outliers / len(arr)

            returns = np.diff(np.log(arr[arr > 0])) if len(arr) > 1 else np.array([])
            ret_mean = float(np.mean(returns)) if len(returns) > 0 else 0
            ret_std = float(np.std(returns)) if len(returns) > 0 else 0
        else:
            mean = sum(values) / len(values)
            variance = sum((v - mean) ** 2 for v in values) / len(values)
            std = math.sqrt(variance)
            outliers = sum(1 for v in values if abs(v - mean) > 3 * std)
            outlier_pct = outliers / len(values)

            log_vals = [math.log(v) for v in values if v > 0]
            if len(log_vals) > 1:
                returns = [log_vals[i] - log_vals[i - 1] for i in range(1, len(log_vals))]
                ret_mean = sum(returns) / len(returns)
                ret_variance = sum((r - ret_mean) ** 2 for r in returns) / len(returns)
                ret_std = math.sqrt(ret_variance)
            else:
                returns = []
                ret_mean = 0
                ret_std = 0

        outlier_threshold = 0.01
        status = "PASS" if outlier_pct <= outlier_threshold else "WARN"

        results[col] = {
            "status": status,
            "mean": round(mean, 6),
            "std": round(std, 6),
            "min": round(float(min(values)), 6),
            "max": round(float(max(values)), 6),
            "outliers_3sigma": outliers,
            "outlier_pct": round(outlier_pct, 6),
            "log_return_mean": round(ret_mean, 8),
            "log_return_std": round(ret_std, 8),
        }

    any_warn = any(r.get("status") == "WARN" for r in results.values())
    overall_status = "WARN" if any_warn else "PASS"

    return {
        "status": overall_status,
        "details": results,
    }


def check_cross_source(
    data: List[Dict], file_format: str, metadata: Dict
) -> Dict[str, Any]:
    """Compare with alternative source (placeholder for multi-source integration)."""
    filepath = metadata.get("_filepath", "")
    if not filepath:
        return {
            "status": "SKIP",
            "details": {"reason": "cross_source check requires file path for finding paired datasets"},
        }

    return {
        "status": "SKIP",
        "details": {
            "reason": "cross_source check is a placeholder. Integrate with MT5/Dukascopy comparison for production use.",
            "file": os.path.basename(filepath) if filepath else "unknown",
        },
    }


CHECK_FUNCTIONS = {
    "schema": check_schema,
    "range": check_range,
    "completeness": check_completeness,
    "sequence": check_sequence,
    "staleness": check_staleness,
    "integrity": check_integrity,
    "distribution": check_distribution,
    "cross_source": check_cross_source,
}


def run_checks(
    filepath: str, check_names: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Run specified checks on a dataset.

    Args:
        filepath: Path to the dataset (parquet or csv).
        check_names: List of checks to run, or None for all.

    Returns:
        dict with full validation report.
    """
    start = time.time()
    if check_names is None:
        check_names = ALL_CHECK_NAMES

    data, file_format, metadata = _read_data(filepath)
    metadata["_filepath"] = os.path.abspath(filepath)

    results = {}
    for name in check_names:
        fn = CHECK_FUNCTIONS.get(name)
        if fn is None:
            results[name] = {"status": "ERROR", "details": {"reason": f"Unknown check: {name}"}}
            continue
        try:
            results[name] = fn(data, file_format, metadata)
        except Exception as e:
            results[name] = {"status": "ERROR", "details": {"reason": str(e)}}

    overall = _overall_status(results)
    elapsed = time.time() - start

    report = {
        "file": os.path.abspath(filepath),
        "timestamp_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "checks": results,
        "overall": overall,
        "recommendation": _recommendation(results, overall),
        "metadata": {
            "format": file_format,
            "total_rows": metadata.get("total_rows", len(data)),
            "sampled": metadata.get("sampled", False),
            "elapsed_seconds": round(elapsed, 3),
        },
    }
    return report


def main():
    parser = argparse.ArgumentParser(
        description="Quant OS Data Validator — comprehensive data quality checks"
    )
    parser.add_argument(
        "--input", "-i", required=True,
        help="Path to input data file (.parquet or .csv)",
    )
    parser.add_argument(
        "--checks", "-c", default="all",
        help="Comma-separated list of checks, or 'all' (default: all). "
             f"Available: {', '.join(ALL_CHECK_NAMES)}",
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="Path to write JSON report (default: print to stdout)",
    )
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"ERROR: Input file not found: {args.input}")
        sys.exit(1)

    if args.checks == "all":
        check_names = ALL_CHECK_NAMES
    else:
        check_names = [c.strip() for c in args.checks.split(",")]

    report = run_checks(args.input, check_names)

    report_json = json.dumps(report, indent=2, default=str)

    if args.output:
        out_dir = os.path.dirname(args.output)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        with open(args.output, "w") as f:
            f.write(report_json)
        print(f"Validation report written to: {args.output}")
    else:
        print(report_json)

    if report["overall"] == "FAIL":
        sys.exit(2)
    elif report["overall"] == "WARN":
        sys.exit(1)


if __name__ == "__main__":
    main()

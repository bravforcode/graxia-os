"""
Data Quality Gate for Quant OS

Validates data before it's used in trading decisions.
Provides both class-based and orchestrator-level quality checks.

Usage:
    from data.quality_gate import run_quality_gate
    result = run_quality_gate("data/EURUSD_M15.csv", checks=["schema", "range"])
"""

import json
import logging
import math
import os
from datetime import UTC, datetime
from typing import Any

from ..core.enums import DataQualityCheck

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFESTS_DIR = os.path.join(PROJECT_ROOT, "data", "manifests")


class QualityCheckResult:
    """Result of a data quality check."""

    def __init__(
        self,
        check_name: DataQualityCheck,
        passed: bool,
        details: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ):
        self.check_name = check_name
        self.passed = passed
        self.details = details or {}
        self.timestamp = timestamp or datetime.now(UTC)


class DataQualityGate:
    """
    Data Quality Gate

    Validates data integrity before trading:
    - Missing timestamps
    - Duplicate timestamps
    - Outlier prices
    - Stale quotes
    - Zero volume
    """

    def __init__(self):
        self.thresholds = {
            "max_price_spike_pct": 5.0,
            "max_staleness_seconds": 60,
            "min_volume_threshold": 1,
        }

    def validate_ohlcv(self, data: list[dict]) -> list[QualityCheckResult]:
        """Validate OHLCV data series."""
        results = []
        results.append(self._check_missing_timestamps(data))
        results.append(self._check_duplicate_timestamps(data))
        results.append(self._check_outlier_prices(data))
        results.append(self._check_zero_volume(data))
        results.append(self._check_stale_quotes(data))
        return results

    def _check_missing_timestamps(self, data: list[dict]) -> QualityCheckResult:
        """Check for missing timestamps."""
        missing = [d for d in data if not d.get("timestamp")]
        return QualityCheckResult(
            check_name=DataQualityCheck.MISSING_TIMESTAMP,
            passed=len(missing) == 0,
            details={"missing_count": len(missing)},
        )

    def _check_duplicate_timestamps(self, data: list[dict]) -> QualityCheckResult:
        """Check for duplicate timestamps."""
        timestamps = [d.get("timestamp") for d in data if d.get("timestamp")]
        duplicates = len(timestamps) - len(set(timestamps))
        return QualityCheckResult(
            check_name=DataQualityCheck.DUPLICATE_TIMESTAMP,
            passed=duplicates == 0,
            details={"duplicate_count": duplicates},
        )

    def _check_outlier_prices(self, data: list[dict]) -> QualityCheckResult:
        """Check for price outliers using spike percentage."""
        if len(data) < 2:
            return QualityCheckResult(check_name=DataQualityCheck.OUTLIER_PRICE, passed=True)

        prices = [d.get("close", 0) for d in data if d.get("close")]
        if not prices:
            return QualityCheckResult(check_name=DataQualityCheck.OUTLIER_PRICE, passed=True)

        avg_price = sum(prices) / len(prices)
        max_spike = max(abs(p - avg_price) / avg_price * 100 for p in prices) if avg_price > 0 else 0

        return QualityCheckResult(
            check_name=DataQualityCheck.OUTLIER_PRICE,
            passed=max_spike < self.thresholds["max_price_spike_pct"],
            details={
                "max_spike_pct": max_spike,
                "threshold": self.thresholds["max_price_spike_pct"],
            },
        )

    def _check_zero_volume(self, data: list[dict]) -> QualityCheckResult:
        """Check for zero volume bars."""
        zero_vol = [d for d in data if d.get("volume", 0) == 0]
        return QualityCheckResult(
            check_name=DataQualityCheck.ZERO_VOLUME,
            passed=len(zero_vol) == 0 or len(zero_vol) < len(data) * 0.1,
            details={"zero_volume_count": len(zero_vol)},
        )

    def _check_stale_quotes(self, data: list[dict]) -> QualityCheckResult:
        """Check for stale quotes."""
        if not data:
            return QualityCheckResult(check_name=DataQualityCheck.STALE_QUOTE, passed=True)

        latest = data[-1]
        latest_ts = latest.get("timestamp")

        if isinstance(latest_ts, datetime):
            age_seconds = (datetime.now(UTC) - latest_ts).total_seconds()
            return QualityCheckResult(
                check_name=DataQualityCheck.STALE_QUOTE,
                passed=age_seconds < self.thresholds["max_staleness_seconds"],
                details={"staleness_seconds": age_seconds},
            )

        return QualityCheckResult(check_name=DataQualityCheck.STALE_QUOTE, passed=True)

    def all_checks_passed(self, results: list[QualityCheckResult]) -> bool:
        """Check if all quality checks passed."""
        return all(r.passed for r in results)


def _find_manifest(filepath: str) -> str | None:
    """Find an existing manifest for the given file."""
    basename = os.path.splitext(os.path.basename(filepath))[0]
    for suffix in [".manifest.json", "_manifest.json"]:
        candidate = os.path.join(MANIFESTS_DIR, f"{basename}{suffix}")
        if os.path.exists(candidate):
            return candidate
    return None


def run_quality_gate(
    filepath: str,
    checks: list[str] | None = None,
) -> dict[str, Any]:
    """Run all applicable quality checks on a dataset.

    Args:
        filepath: Path to the data file (parquet or csv).
        checks: List of checks to run, or None for all applicable checks.

    Returns:
        dict with keys:
            - file: absolute file path
            - timestamp_utc: ISO timestamp of the run
            - checks: dict of check_name -> {status, details}
            - overall: PASS | WARN | FAIL
            - recommendation: human-readable action text

    Example:
        >>> result = run_quality_gate("data/EURUSD_M15.csv")
        >>> print(result["overall"])
        PASS
    """
    absolute_path = os.path.abspath(filepath)
    logger.info(f"Running quality gate on: {absolute_path}")

    if not os.path.exists(absolute_path):
        logger.error(f"File not found: {absolute_path}")
        return {
            "file": absolute_path,
            "timestamp_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "checks": {"file_exists": {"status": "FAIL", "details": {"reason": "File not found"}}},
            "overall": "FAIL",
            "recommendation": "File does not exist. Check the path and try again.",
        }

    all_check_names = [
        "file_exists",
        "schema",
        "range",
        "completeness",
        "sequence",
        "staleness",
        "integrity",
        "distribution",
    ]
    if checks is not None:
        selected = [c for c in all_check_names if c in checks or c == "file_exists"]
    else:
        selected = all_check_names

    results = {}

    # file_exists is implicit
    results["file_exists"] = {"status": "PASS", "details": {"path": absolute_path}}

    ext = os.path.splitext(filepath)[1].lower()
    if ext not in (".parquet", ".csv"):
        results["format"] = {"status": "FAIL", "details": {"reason": f"Unsupported format: {ext}"}}
        return _finalize(absolute_path, results)

    rows = _read_data_safe(absolute_path, ext)
    if rows is None:
        results["read"] = {"status": "FAIL", "details": {"reason": "Failed to read data"}}
        return _finalize(absolute_path, results)

    # Derive dataset type from columns
    columns = list(rows[0].keys()) if rows else []
    ds_type = _infer_dataset_type(columns)

    gate = DataQualityGate()

    if "schema" in selected:
        results["schema"] = _check_schema_gate(columns, ds_type, rows)
    if "range" in selected:
        results["range"] = _check_range_gate(rows, ds_type)
    if "completeness" in selected:
        results["completeness"] = _check_completeness_gate(rows)
    if "sequence" in selected:
        results["sequence"] = _check_sequence_gate(rows, columns)
    if "staleness" in selected:
        results["staleness"] = _check_staleness_gate(rows, columns)
    if "integrity" in selected:
        results["integrity"] = _check_integrity_gate(absolute_path)
    if "distribution" in selected:
        results["distribution"] = _check_distribution_gate(rows, ds_type)

    return _finalize(absolute_path, results)


def _finalize(filepath: str, results: dict) -> dict[str, Any]:
    """Build the final report dict from raw check results."""
    has_fail = any(r.get("status") == "FAIL" for r in results.values())
    has_warn = any(r.get("status") == "WARN" for r in results.values())

    if has_fail:
        overall = "FAIL"
    elif has_warn:
        overall = "WARN"
    else:
        overall = "PASS"

    fails = [k for k, v in results.items() if v.get("status") == "FAIL"]
    warns = [k for k, v in results.items() if v.get("status") == "WARN"]

    parts = []
    if fails:
        parts.append(f"Failing checks: {', '.join(fails)}. Do not use this dataset until resolved.")
    if warns:
        parts.append(f"Warnings: {', '.join(warns)}. Review before production use.")
    recommendation = " ".join(parts) if parts else "Dataset passed all checks. Ready for pipeline."

    report = {
        "file": filepath,
        "timestamp_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "checks": results,
        "overall": overall,
        "recommendation": recommendation,
    }
    logger.info(f"Quality gate result: {overall}")
    return report


def _read_data_safe(filepath: str, ext: str) -> list[dict] | None:
    """Safely read data, returning None on failure."""
    try:
        if ext == ".parquet":
            try:
                import pandas as pd

                df = pd.read_parquet(filepath)
                if len(df) > 100000:
                    df = df.head(100000)
                return df.to_dict("records")
            except ImportError:
                import pyarrow.parquet as pq

                pf = pq.ParquetFile(filepath)
                n = min(pf.metadata.num_rows, 100000)
                table = pf.read_rows(0, n)
                return table.to_pylist()
        elif ext == ".csv":
            import csv

            rows = []
            with open(filepath, newline="") as f:
                reader = csv.DictReader(f)
                for i, row in enumerate(reader):
                    if i >= 100000:
                        break
                    rows.append(row)
            return rows
    except Exception as e:
        logger.error(f"Failed to read {filepath}: {e}")
        return None


def _infer_dataset_type(columns: list[str]) -> str:
    """Detect tick vs OHLCV dataset."""
    col_set = set(col.lower() for col in columns)
    if {"bid", "ask"}.issubset(col_set):
        return "tick"
    if {"open", "high", "low", "close"}.issubset(col_set):
        return "ohlcv"
    return "unknown"


def _check_schema_gate(columns: list[str], ds_type: str, data: list[dict]) -> dict:
    """Verify column presence matches expected contract."""
    if ds_type == "tick":
        expected = {"timestamp", "bid", "ask", "spread_points", "symbol", "source"}
    elif ds_type == "ohlcv":
        expected = {"time", "open", "high", "low", "close", "volume"}
    else:
        return {"status": "SKIP", "details": {"reason": "Unknown dataset type for schema check"}}

    col_set = set(col.lower() for col in columns)
    missing = expected - col_set
    null_cols = {}
    for col in expected & col_set:
        nulls = sum(1 for row in data if row.get(col) is None or str(row.get(col, "")).strip() == "")
        if nulls > 0:
            null_cols[col] = nulls

    passed = len(missing) == 0 and len(null_cols) == 0
    return {
        "status": "PASS" if passed else "FAIL",
        "details": {
            "columns_found": columns,
            "columns_expected": sorted(expected),
            "missing_columns": sorted(missing),
            "null_columns": null_cols,
        },
    }


def _check_range_gate(data: list[dict], ds_type: str) -> dict:
    """Verify bid/ask/price ranges."""
    violations = 0
    violation_sample = []
    for i, row in enumerate(data):
        bid = _to_float(row.get("bid"))
        ask = _to_float(row.get("ask"))
        if bid is not None and bid <= 0:
            violations += 1
            if len(violation_sample) < 5:
                violation_sample.append({"row": i, "field": "bid", "value": bid})
        if ask is not None and ask <= 0:
            violations += 1
            if len(violation_sample) < 5:
                violation_sample.append({"row": i, "field": "ask", "value": ask})
        if bid is not None and ask is not None and ask < bid:
            violations += 1
            if len(violation_sample) < 5:
                violation_sample.append({"row": i, "field": "spread", "value": ask - bid})
        if ds_type == "ohlcv":
            for col in ("open", "high", "low", "close"):
                val = _to_float(row.get(col))
                if val is not None and (val < 0.5 or val > 200):
                    violations += 1
                    if len(violation_sample) < 5:
                        violation_sample.append({"row": i, "field": col, "value": val})
        if violations >= 10000:
            break

    threshold = 0.001
    violation_pct = violations / max(len(data), 1)
    passed = violation_pct <= threshold
    return {
        "status": "PASS" if passed else "FAIL",
        "violations": violations,
        "threshold": threshold,
        "sample": violation_sample,
        "details": {"violation_rate": round(violation_pct, 6)},
    }


def _check_completeness_gate(data: list[dict]) -> dict:
    """Check row count expectation and detect gaps."""
    actual = len(data)
    if actual == 0:
        return {"status": "FAIL", "details": {"reason": "Dataset is empty"}}
    return {"status": "PASS", "details": {"rows_loaded": actual}}


def _infer_bar_interval_sec(timestamps: list) -> float | None:
    """Infer typical bar interval from first N intervals (median)."""
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
    sorted_gaps = sorted(gaps)
    return float(sorted_gaps[len(sorted_gaps) // 2])


def _check_sequence_gate(data: list[dict], columns: list[str]) -> dict:
    """Check timestamps strictly increasing, no duplicates."""
    if not data:
        return {"status": "PASS", "details": {"reason": "No data"}}
    ts_col = "timestamp" if "timestamp" in columns else "time"
    timestamps = []
    for row in data:
        ts = row.get(ts_col)
        if ts is not None:
            timestamps.append(ts)
    if len(timestamps) < 2:
        return {"status": "PASS", "details": {"reason": "Insufficient timestamps"}}

    seen = set()
    duplicates = 0
    decreasing = 0
    for i, ts in enumerate(timestamps):
        ts_str = str(ts)
        if ts_str in seen:
            duplicates += 1
        seen.add(ts_str)
        if i > 0:
            t_prev = _parse_ts(timestamps[i - 1])
            t_cur = _parse_ts(ts)
            if t_prev and t_cur and t_cur <= t_prev:
                decreasing += 1

    status = "FAIL" if (duplicates > 0 or decreasing > 0) else "PASS"
    return {
        "status": status,
        "details": {
            "total_timestamps": len(timestamps),
            "duplicate_count": duplicates,
            "out_of_order_count": decreasing,
        },
    }


def _check_staleness_gate(data: list[dict], columns: list[str]) -> dict:
    """Detect time gaps between consecutive rows.

    Adaptive threshold: 30s for ticks, 3x bar interval for OHLCV.
    """
    ds_type = _infer_dataset_type(columns)
    ts_col = "timestamp" if "timestamp" in columns else "time"
    timestamps = []
    for row in data:
        ts = row.get(ts_col)
        if ts is not None:
            timestamps.append(ts)
    if len(timestamps) < 2:
        return {"status": "PASS", "details": {"reason": "Insufficient timestamps"}}

    base_threshold = 30
    if ds_type == "ohlcv":
        interval = _infer_bar_interval_sec(timestamps)
        if interval and interval > 0:
            base_threshold = interval * 3

    max_gap = 0
    for i in range(1, len(timestamps)):
        try:
            t_prev = _parse_ts(timestamps[i - 1])
            t_cur = _parse_ts(timestamps[i])
            if t_prev and t_cur:
                gap = (t_cur - t_prev).total_seconds()
                if gap > max_gap:
                    max_gap = gap
        except Exception:
            pass

    status = "WARN" if max_gap > base_threshold else "PASS"
    return {
        "status": status,
        "details": {
            "max_gap_seconds": round(max_gap, 2),
            "threshold_seconds": base_threshold,
        },
    }


def _check_integrity_gate(filepath: str) -> dict:
    """Verify SHA-256 against manifest if available."""
    import hashlib

    h = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except Exception as e:
        return {"status": "ERROR", "details": {"reason": str(e)}}
    actual_hash = h.hexdigest()

    manifest_path = _find_manifest(filepath)
    if manifest_path is None:
        return {
            "status": "WARN",
            "details": {
                "reason": "No manifest found to verify against",
                "computed_sha256": actual_hash[:32] + "...",
            },
        }
    with open(manifest_path) as f:
        manifest = json.load(f)
    expected = manifest.get("sha256") or manifest.get("csv_sha256")
    if expected is None:
        return {"status": "WARN", "details": {"reason": "Manifest has no sha256 field"}}
    passed = actual_hash == expected
    return {
        "status": "PASS" if passed else "FAIL",
        "details": {
            "manifest_path": manifest_path,
            "hash_match": passed,
        },
    }


def _check_distribution_gate(data: list[dict], ds_type: str) -> dict:
    """Check price distribution sanity using 3-sigma outlier detection."""
    price_cols = []
    if ds_type == "tick":
        price_cols = ["bid", "ask"]
    elif ds_type == "ohlcv":
        price_cols = ["close"]
    if not price_cols:
        return {"status": "SKIP", "details": {"reason": "No price columns found"}}

    sample_size = min(500000, len(data))
    if sample_size < 10:
        return {"status": "SKIP", "details": {"reason": f"Insufficient data (n={sample_size})"}}

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
            ret_mean = 0
            ret_std = 0

        status = "PASS" if outlier_pct <= 0.01 else "WARN"
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
    return {
        "status": "WARN" if any_warn else "PASS",
        "details": results,
    }


def _to_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _parse_ts(val):
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

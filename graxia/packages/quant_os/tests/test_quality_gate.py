"""Tests for data.quality_gate — orchestrator + DataQualityGate class."""

from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
from pathlib import Path

from quant_os.core.enums import DataQualityCheck

from graxia.packages.quant_os.data.quality_gate import (
    DataQualityGate,
    QualityCheckResult,
    run_quality_gate,
)


def _write_csv(path: Path, rows: list[dict]) -> None:
    """Write a CSV with the given dict rows."""
    if not rows:
        path.write_text("")
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _make_clean_ohlcv_rows(n: int = 10) -> list[dict]:
    """Build a small, well-formed OHLCV row set."""
    base_ts = datetime(2024, 1, 15, 8, 0, tzinfo=UTC)
    rows = []
    for i in range(n):
        ts = base_ts + timedelta(minutes=15 * i)
        rows.append(
            {
                "time": ts.isoformat(),
                "open": 100.0 + i,
                "high": 101.0 + i,
                "low": 99.0 + i,
                "close": 100.5 + i,
                "volume": 1000 + i,
            }
        )
    return rows


class TestRunQualityGate:
    def test_run_quality_gate_csv_passes(self, tmp_path: Path):
        """A small clean CSV should pass the orchestrator-level checks."""
        rows = _make_clean_ohlcv_rows(20)
        f = tmp_path / "clean_ohlcv.csv"
        _write_csv(f, rows)

        result = run_quality_gate(str(f))
        assert result["overall"] in ("PASS", "WARN"), result
        assert "file_exists" in result["checks"]
        assert result["checks"]["file_exists"]["status"] == "PASS"
        # Schema should be detected as ohlcv and pass (or warn on small N).
        assert "schema" in result["checks"]
        # All file checks at least ran.
        assert "completeness" in result["checks"]
        assert "sequence" in result["checks"]
        assert "distribution" in result["checks"]

    def test_run_quality_gate_csv_missing(self, tmp_path: Path):
        """Missing file → FAIL with 'File not found' in the reason."""
        missing = tmp_path / "does_not_exist.csv"
        result = run_quality_gate(str(missing))
        assert result["overall"] == "FAIL"
        assert result["checks"]["file_exists"]["status"] == "FAIL"
        assert "File not found" in result["checks"]["file_exists"]["details"]["reason"]

    def test_run_quality_gate_detects_unsorted(self, tmp_path: Path):
        """Out-of-order timestamps should fail the sequence check."""
        # Build a sorted row set, then shuffle two adjacent rows.
        rows = _make_clean_ohlcv_rows(20)
        # Swap the timestamps of rows 5 and 6 to break monotonicity.
        rows[5]["time"], rows[6]["time"] = rows[6]["time"], rows[5]["time"]
        f = tmp_path / "unsorted.csv"
        _write_csv(f, rows)

        result = run_quality_gate(str(f))
        # Sequence check should detect out-of-order (FAIL or WARN)
        seq = result["checks"]["sequence"]
        assert seq["status"] in ("FAIL", "WARN")
        # Overall should not be PASS when timestamps are out of order
        assert result["overall"] != "PASS"
        # Should report out-of-order count > 0.
        assert seq["details"]["out_of_order_count"] > 0

    def test_run_quality_gate_detects_outliers(self, tmp_path: Path):
        """Synthetic outliers in close price should warn the distribution check."""
        rows = _make_clean_ohlcv_rows(100)
        # Add 5 extreme prices to push >1% of rows beyond 3-sigma.
        for i in (10, 30, 50, 70, 90):
            rows[i]["close"] = 1000.0 + i  # huge spike
        f = tmp_path / "outliers.csv"
        _write_csv(f, rows)

        result = run_quality_gate(str(f))
        dist = result["checks"]["distribution"]
        # Distribution should be WARN, and overall should not be PASS.
        assert dist["status"] == "WARN"
        assert result["overall"] in ("WARN", "FAIL")


class TestDataQualityGate:
    def test_data_quality_gate_check_zero_volume(self):
        """All-zero volume rows are flagged; <10% zero volumes is acceptable."""
        gate = DataQualityGate()
        # 10 rows, 0 zero-volume → passed (since <10% rule)
        data = [
            {"timestamp": "2024-01-01", "close": 100.0, "volume": 100},
            {"timestamp": "2024-01-02", "close": 101.0, "volume": 100},
            {"timestamp": "2024-01-03", "close": 102.0, "volume": 100},
        ]
        result = gate._check_zero_volume(data)
        assert isinstance(result, QualityCheckResult)
        assert result.check_name == DataQualityCheck.ZERO_VOLUME
        assert result.passed is True
        assert result.details["zero_volume_count"] == 0

        # 5 rows all zero volume → >10% rule trips.
        data_zero = [{"timestamp": f"2024-01-0{i+1}", "close": 100.0, "volume": 0} for i in range(5)]
        result2 = gate._check_zero_volume(data_zero)
        assert result2.passed is False
        assert result2.details["zero_volume_count"] == 5

    def test_data_quality_gate_missing_timestamps(self):
        """Rows without a timestamp flag the MISSING_TIMESTAMP check."""
        gate = DataQualityGate()
        data = [
            {"timestamp": "2024-01-01", "close": 100.0, "volume": 100},
            {"close": 101.0, "volume": 100},  # missing timestamp
            {"timestamp": "2024-01-03", "close": 102.0, "volume": 100},
        ]
        r = gate._check_missing_timestamps(data)
        assert r.check_name == DataQualityCheck.MISSING_TIMESTAMP
        assert r.passed is False
        assert r.details["missing_count"] == 1

    def test_data_quality_gate_duplicate_timestamps(self):
        """Two rows with the same timestamp trip the DUPLICATE_TIMESTAMP check."""
        gate = DataQualityGate()
        data = [
            {"timestamp": "2024-01-01", "close": 100.0},
            {"timestamp": "2024-01-01", "close": 100.5},
            {"timestamp": "2024-01-02", "close": 101.0},
        ]
        r = gate._check_duplicate_timestamps(data)
        assert r.passed is False
        assert r.details["duplicate_count"] == 1

    def test_data_quality_gate_all_checks_passed_helper(self):
        """all_checks_passed returns True only when every result is passed=True."""
        gate = DataQualityGate()
        passed = QualityCheckResult(check_name=DataQualityCheck.ZERO_VOLUME, passed=True)
        failed = QualityCheckResult(check_name=DataQualityCheck.ZERO_VOLUME, passed=False)
        assert gate.all_checks_passed([passed, passed]) is True
        assert gate.all_checks_passed([passed, failed]) is False

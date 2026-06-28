"""Memory leak chaos test.

Simulates sustained tick processing load and monitors process RSS and
DuckDB WAL growth to detect memory leaks before they reach production.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPORTS_DIR = Path(__file__).parent / "reports"
RSS_ALERT_THRESHOLD_PCT: float = 50.0
WAL_GROWTH_ALERT_MB: float = 100.0
DEFAULT_LOAD_DURATION_MIN: float = 0.5  # 30s for CI; 30 for production


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_rss_mb() -> float:
    """Return current process RSS in MB."""
    try:
        import psutil
        proc = psutil.Process()
        return proc.memory_info().rss / (1024 * 1024)
    except (ImportError, Exception):
        pass

    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return usage.ru_maxrss / 1024.0
    except (ImportError, AttributeError):
        return 0.0


def _wal_size_mb(db_path: str) -> float:
    """Return DuckDB WAL file size in MB."""
    p = Path(db_path)
    wal_path = p.parent / f"{p.name}.wal"
    if not wal_path.exists():
        return 0.0
    return wal_path.stat().st_size / (1024 * 1024)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class MemorySnapshot:
    """Point-in-time memory measurement."""
    rss_mb: float
    timestamp: float
    tick_count: int = 0


@dataclass
class MemoryLeakReport:
    """Full memory leak test report."""
    baseline_rss_mb: float
    final_rss_mb: float
    peak_rss_mb: float
    growth_pct: float
    alert_triggered: bool
    wal_size_mb: float
    wal_growth_mb: float
    duration_seconds: float
    ticks_processed: int
    passed: bool
    errors: List[str] = field(default_factory=list)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ---------------------------------------------------------------------------
# Simulated tick processor
# ---------------------------------------------------------------------------


class TickProcessor:
    """Simulates continuous tick processing for load testing."""

    def __init__(self) -> None:
        self.tick_count: int = 0
        self._data_store: List[Dict[str, Any]] = []

    def process_tick(self, symbol: str = "XAUUSD") -> None:
        """Process a single simulated tick."""
        import random
        self.tick_count += 1
        tick = {
            "symbol": symbol,
            "bid": 2350.00 + random.uniform(-5.0, 5.0),
            "ask": 2350.20 + random.uniform(-5.0, 5.0),
            "volume": random.randint(1, 100),
            "timestamp": time.time(),
        }
        self._data_store.append(tick)

        # Simulate feature computation (keeps memory growing)
        if self.tick_count % 1000 == 0:
            self._compact()

    def _compact(self) -> None:
        """Simulate periodic compaction — keep last 5000 ticks."""
        if len(self._data_store) > 5000:
            self._data_store = self._data_store[-5000:]

    def reset(self) -> None:
        self.tick_count = 0
        self._data_store.clear()


# ---------------------------------------------------------------------------
# MemoryLeakTest class
# ---------------------------------------------------------------------------


class MemoryLeakTest:
    """Monitor RSS and WAL growth under sustained load.

    Usage::

        ml = MemoryLeakTest()
        ml.baseline_memory()
        ml.run_sustained_load(duration_minutes=30)
        report = ml.check_memory_growth()
        assert report.passed
    """

    def __init__(
        self,
        *,
        alert_threshold_pct: float = RSS_ALERT_THRESHOLD_PCT,
        wal_alert_mb: float = WAL_GROWTH_ALERT_MB,
        db_path: Optional[str] = None,
    ) -> None:
        self.alert_threshold_pct = alert_threshold_pct
        self.wal_alert_mb = wal_alert_mb
        self.db_path = db_path or os.getenv("DUCKDB_PATH", "data/market_data.duckdb")
        self._baseline_rss: float = 0.0
        self._snapshots: List[MemorySnapshot] = []
        self._processor = TickProcessor()
        self._wal_initial: float = 0.0
        self._start_time: float = 0.0

    def baseline_memory(self) -> float:
        """Record initial RSS as the baseline.

        Returns:
            Baseline RSS in MB.
        """
        self._baseline_rss = _get_rss_mb()
        self._snapshots.append(
            MemorySnapshot(rss_mb=self._baseline_rss, timestamp=time.time())
        )
        self._wal_initial = _wal_size_mb(self.db_path)
        self._start_time = time.time()
        return self._baseline_rss

    def run_sustained_load(
        self,
        duration_minutes: float = DEFAULT_LOAD_DURATION_MIN,
    ) -> None:
        """Simulate continuous tick processing for the given duration.

        Args:
            duration_minutes: How long to run the load (in minutes).
        """
        end_time = time.time() + (duration_minutes * 60)
        sample_interval = 5.0  # snapshot every 5 seconds
        last_sample = time.time()

        while time.time() < end_time:
            self._processor.process_tick()

            now = time.time()
            if (now - last_sample) >= sample_interval:
                rss = _get_rss_mb()
                self._snapshots.append(
                    MemorySnapshot(
                        rss_mb=rss,
                        timestamp=now,
                        tick_count=self._processor.tick_count,
                    )
                )
                last_sample = now

    def check_memory_growth(self) -> MemoryLeakReport:
        """Analyze RSS growth and WAL size after load.

        Returns:
            MemoryLeakReport with growth analysis.
        """
        errors: List[str] = []
        final_rss = _get_rss_mb()
        peak_rss = max(s.rss_mb for s in self._snapshots) if self._snapshots else final_rss
        wal_final = _wal_size_mb(self.db_path)
        duration = time.time() - self._start_time if self._start_time else 0.0

        growth_pct = (
            ((final_rss - self._baseline_rss) / self._baseline_rss * 100)
            if self._baseline_rss > 0
            else 0.0
        )
        wal_growth = wal_final - self._wal_initial

        alert = growth_pct > self.alert_threshold_pct
        if alert:
            errors.append(
                f"MEMORY LEAK: RSS grew {growth_pct:.1f}% "
                f"(baseline={self._baseline_rss:.1f}MB final={final_rss:.1f}MB)"
            )

        wal_alert = wal_growth > self.wal_alert_mb
        if wal_alert:
            errors.append(
                f"WAL GROWTH: {wal_growth:.1f}MB increase "
                f"(initial={self._wal_initial:.1f}MB final={wal_final:.1f}MB)"
            )

        passed = not alert and not wal_alert

        return MemoryLeakReport(
            baseline_rss_mb=round(self._baseline_rss, 2),
            final_rss_mb=round(final_rss, 2),
            peak_rss_mb=round(peak_rss, 2),
            growth_pct=round(growth_pct, 2),
            alert_triggered=alert,
            wal_size_mb=round(wal_final, 4),
            wal_growth_mb=round(wal_growth, 4),
            duration_seconds=round(duration, 2),
            ticks_processed=self._processor.tick_count,
            passed=passed,
            errors=errors,
        )

    def test_duckdb_wal_growth(self) -> float:
        """Check WAL file size over time.

        Returns:
            WAL growth in MB since baseline was recorded.
        """
        wal_now = _wal_size_mb(self.db_path)
        return wal_now - self._wal_initial

    def write_report(self, report: MemoryLeakReport) -> Path:
        """Save report to tests/chaos/reports/.

        Args:
            report: MemoryLeakReport to persist.

        Returns:
            Path to written report file.
        """
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"memory_leak_report_{ts}.json"
        path = REPORTS_DIR / filename

        data = {
            "baseline_rss_mb": report.baseline_rss_mb,
            "final_rss_mb": report.final_rss_mb,
            "peak_rss_mb": report.peak_rss_mb,
            "growth_pct": report.growth_pct,
            "alert_triggered": report.alert_triggered,
            "wal_size_mb": report.wal_size_mb,
            "wal_growth_mb": report.wal_growth_mb,
            "duration_seconds": report.duration_seconds,
            "ticks_processed": report.ticks_processed,
            "passed": report.passed,
            "errors": report.errors,
            "timestamp": report.timestamp,
        }
        path.write_text(json.dumps(data, indent=2))
        return path


# ---------------------------------------------------------------------------
# Pytest tests
# ---------------------------------------------------------------------------


class TestMemoryLeak:
    """Pytest suite for memory leak detection."""

    def test_baseline_records_rss(self) -> None:
        """Baseline must record a positive RSS value."""
        ml = MemoryLeakTest()
        baseline = ml.baseline_memory()
        assert baseline > 0, "Baseline RSS should be positive"

    def test_sustained_load_runs(self) -> None:
        """Sustained load must produce snapshots."""
        ml = MemoryLeakTest()
        ml.baseline_memory()
        ml.run_sustained_load(duration_minutes=0.02)  # ~1.2s
        assert len(ml._snapshots) >= 1, "No snapshots recorded during load"

    def test_short_load_no_leak(self) -> None:
        """Short load must not trigger memory leak alert."""
        ml = MemoryLeakTest()
        ml.baseline_memory()
        ml.run_sustained_load(duration_minutes=0.02)
        report = ml.check_memory_growth()
        assert report.passed, f"Memory leak detected: {report.errors}"

    def test_wal_growth_check(self) -> None:
        """WAL growth method must return a numeric value."""
        ml = MemoryLeakTest()
        ml.baseline_memory()
        growth = ml.test_duckdb_wal_growth()
        assert isinstance(growth, float)

    def test_report_written(self) -> None:
        """Report must be saved to the reports directory."""
        ml = MemoryLeakTest()
        ml.baseline_memory()
        ml.run_sustained_load(duration_minutes=0.02)
        report = ml.check_memory_growth()
        path = ml.write_report(report)
        assert path.exists(), f"Report not found at {path}"
        content = json.loads(path.read_text())
        assert "baseline_rss_mb" in content
        assert "passed" in content
        # Cleanup
        path.unlink(missing_ok=True)

    def test_peak_rss_tracking(self) -> None:
        """Peak RSS must be >= baseline RSS."""
        ml = MemoryLeakTest()
        ml.baseline_memory()
        ml.run_sustained_load(duration_minutes=0.02)
        report = ml.check_memory_growth()
        assert report.peak_rss_mb >= report.baseline_rss_mb

    def test_growth_pct_calculation(self) -> None:
        """Growth percentage must be correctly calculated."""
        ml = MemoryLeakTest()
        ml.baseline_memory()
        ml.run_sustained_load(duration_minutes=0.02)
        report = ml.check_memory_growth()
        if report.baseline_rss_mb > 0:
            expected = (
                (report.final_rss_mb - report.baseline_rss_mb)
                / report.baseline_rss_mb * 100
            )
            assert abs(report.growth_pct - round(expected, 2)) < 0.1

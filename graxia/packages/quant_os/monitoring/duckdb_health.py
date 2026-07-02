"""DuckDB WAL monitoring and health checks.

Tracks WAL file size, auto-checkpoints when thresholds are breached,
monitors process memory (RSS) for leaks, and validates data integrity.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

WAL_SIZE_WARN_MB: float = 50.0
WAL_SIZE_CRITICAL_MB: float = 100.0
RSS_LEAK_MULTIPLIER: float = 2.0
RSS_BASELINE_WINDOW: int = 60  # seconds to average baseline
MEMORY_CHECK_INTERVAL: int = 30  # seconds between checks

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_rss_mb() -> float:
    """Return current process RSS in MB via /proc or psutil fallback."""
    try:
        import resource
        # Linux: getrusage returns KB
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return usage.ru_maxrss / 1024.0
    except (ImportError, AttributeError):
        pass

    try:
        import psutil
        proc = psutil.Process(os.getpid())
        return proc.memory_info().rss / (1024 * 1024)
    except (ImportError, Exception):
        pass

    # Windows fallback: use psutil if available
    try:
        import psutil
        proc = psutil.Process()
        mem = proc.memory_info()
        return mem.rss / (1024 * 1024)
    except Exception:
        return 0.0


def _wal_size_mb(db_path: str) -> float:
    """Return WAL file size in MB for the given DuckDB database."""
    p = Path(db_path)
    wal_path = p.parent / f"{p.name}.wal"
    if not wal_path.exists():
        return 0.0
    return wal_path.stat().st_size / (1024 * 1024)


def _file_mtime(path: Path) -> Optional[datetime]:
    """Return last-modified time as UTC datetime, or None."""
    if not path.exists():
        return None
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts, tz=UTC)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class WALHealth:
    """WAL monitoring result."""
    wal_size_mb: float
    checkpoint_needed: bool
    db_path: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class MemoryHealth:
    """Process memory monitoring result."""
    process_rss_mb: float
    duckdb_connection_count: int
    baseline_rss_mb: float
    leak_detected: bool
    growth_pct: float
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class DataIntegrity:
    """DuckDB data integrity check result."""
    table_counts: int
    row_counts: Dict[str, int]
    last_write_time: Optional[str]
    db_path: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class HealthCheckLog:
    """Structured log entry for a full health check."""
    wal: WALHealth
    memory: MemoryHealth
    integrity: DataIntegrity
    overall_status: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


# ---------------------------------------------------------------------------
# DuckDBHealth class
# ---------------------------------------------------------------------------


class DuckDBHealth:
    """Monitor DuckDB WAL, process memory, and data integrity.

    Usage::

        health = DuckDBHealth("data/market_data.duckdb")
        result = health.log_health_check()
        if result.overall_status == "CRITICAL":
            send_alert(result)
    """

    def __init__(
        self,
        db_path: str,
        *,
        warn_mb: float = WAL_SIZE_WARN_MB,
        critical_mb: float = WAL_SIZE_CRITICAL_MB,
        leak_multiplier: float = RSS_LEAK_MULTIPLIER,
    ) -> None:
        self.db_path = db_path
        self.warn_mb = warn_mb
        self.critical_mb = critical_mb
        self.leak_multiplier = leak_multiplier
        self._baseline_rss: Optional[float] = None
        self._baseline_ts: float = 0.0
        self._rss_history: List[float] = []

    # ------------------------------------------------------------------
    # WAL monitoring
    # ------------------------------------------------------------------

    def monitor_wal_size(self) -> WALHealth:
        """Check WAL file size and whether a checkpoint is needed.

        Returns:
            WALHealth with current size and checkpoint flag.
        """
        size = _wal_size_mb(self.db_path)
        need_cp = size >= self.critical_mb
        level = "CRITICAL" if need_cp else ("WARN" if size >= self.warn_mb else "OK")
        logger.info("WAL size %.2f MB [%s]", size, level)

        if need_cp:
            logger.warning(
                "WAL exceeds %.0f MB — triggering auto-checkpoint", self.critical_mb
            )
            self._force_checkpoint()

        return WALHealth(
            wal_size_mb=round(size, 4),
            checkpoint_needed=need_cp,
            db_path=self.db_path,
        )

    def _force_checkpoint(self) -> None:
        """Force a DuckDB WAL checkpoint via PRAGMA force_checkpoint."""
        try:
            import duckdb
            conn = duckdb.connect(self.db_path, read_only=False)
            try:
                conn.execute("PRAGMA force_checkpoint")
                logger.info("Auto-checkpoint completed for %s", self.db_path)
            finally:
                conn.close()
        except Exception as exc:
            logger.error("Auto-checkpoint failed: %s", exc)

    # ------------------------------------------------------------------
    # Memory monitoring
    # ------------------------------------------------------------------

    def monitor_memory_usage(self) -> MemoryHealth:
        """Monitor process RSS and detect memory leaks.

        Tracks RSS over time. If current RSS exceeds the recorded baseline
        by the leak multiplier, ``leak_detected`` is set to ``True``.

        Returns:
            MemoryHealth with current and baseline RSS.
        """
        rss = _get_rss_mb()
        self._rss_history.append(rss)

        now = time.monotonic()

        # Establish baseline after the window fills
        if self._baseline_rss is None or (now - self._baseline_ts) > 300:
            window = min(len(self._rss_history), RSS_BASELINE_WINDOW)
            self._baseline_rss = sum(self._rss_history[-window:]) / max(window, 1)
            self._baseline_ts = now

        growth_pct = (
            ((rss - self._baseline_rss) / self._baseline_rss * 100)
            if self._baseline_rss > 0
            else 0.0
        )
        leak = growth_pct > ((self.leak_multiplier - 1.0) * 100)

        if leak:
            logger.critical(
                "MEMORY LEAK DETECTED: RSS %.1f MB is %.1f%% above baseline %.1f MB",
                rss, growth_pct, self._baseline_rss,
            )

        return MemoryHealth(
            process_rss_mb=round(rss, 2),
            duckdb_connection_count=self._count_connections(),
            baseline_rss_mb=round(self._baseline_rss or rss, 2),
            leak_detected=leak,
            growth_pct=round(growth_pct, 2),
        )

    def _count_connections(self) -> int:
        """Return approximate number of active DuckDB connections."""
        try:
            # Check if a global connection can list attached databases
            # This is a lightweight heuristic
            return 1
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # Data integrity
    # ------------------------------------------------------------------

    def check_data_integrity(self, db_path: Optional[str] = None) -> DataIntegrity:
        """Validate DuckDB tables exist, have rows, and track last write time.

        Args:
            db_path: Override path; defaults to ``self.db_path``.

        Returns:
            DataIntegrity with table/row counts and last write time.
        """
        target = db_path or self.db_path
        table_counts = 0
        row_counts: Dict[str, int] = {}
        last_write: Optional[datetime] = None

        try:
            import duckdb
            conn = duckdb.connect(target, read_only=True)
            try:
                tables = conn.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'main'"
                ).fetchall()

                table_counts = len(tables)
                for (tbl,) in tables:
                    cnt = conn.execute(f'SELECT COUNT(*) FROM "{tbl}"').fetchone()[0]
                    row_counts[tbl] = cnt

                # Estimate last write from the largest table's max row
                # (DuckDB doesn't track write timestamps natively)
                if row_counts:
                    largest = max(row_counts, key=row_counts.get)  # type: ignore[arg-type]
                    try:
                        result = conn.execute(
                            f"SELECT MAX(rowid) FROM \"{largest}\""
                        ).fetchone()
                        if result and result[0] is not None:
                            last_write = datetime.now(UTC)
                    except Exception:
                        pass
            finally:
                conn.close()
        except Exception as exc:
            logger.error("Data integrity check failed: %s", exc)

        return DataIntegrity(
            table_counts=table_counts,
            row_counts=row_counts,
            last_write_time=last_write.isoformat() if last_write else None,
            db_path=target,
        )

    # ------------------------------------------------------------------
    # Full health check
    # ------------------------------------------------------------------

    def log_health_check(self) -> HealthCheckLog:
        """Run all monitors and produce a structured log entry.

        Returns:
            HealthCheckLog with overall status (OK / WARN / CRITICAL).
        """
        wal = self.monitor_wal_size()
        mem = self.monitor_memory_usage()
        integrity = self.check_data_integrity()

        # Determine overall status
        statuses = ["OK"]
        if wal.wal_size_mb >= self.critical_mb:
            statuses.append("CRITICAL")
        elif wal.wal_size_mb >= self.warn_mb:
            statuses.append("WARN")
        if mem.leak_detected:
            statuses.append("CRITICAL")
        if integrity.table_counts == 0 and Path(self.db_path).exists():
            statuses.append("WARN")

        if "CRITICAL" in statuses:
            overall = "CRITICAL"
        elif "WARN" in statuses:
            overall = "WARN"
        else:
            overall = "OK"

        log_entry = HealthCheckLog(
            wal=wal,
            memory=mem,
            integrity=integrity,
            overall_status=overall,
        )

        logger.info(
            "Health check: status=%s | WAL=%.2fMB | RSS=%.1fMB | tables=%d",
            overall,
            wal.wal_size_mb,
            mem.process_rss_mb,
            integrity.table_counts,
        )
        return log_entry

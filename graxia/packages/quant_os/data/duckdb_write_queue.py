"""
DuckDB Write Queue — single-writer pattern for high-throughput ingestion.

Decouples producers (tick ingester, bar aggregator) from the DuckDB writer
using an asyncio.Queue. Batches records for bulk INSERT inside a single
transaction, falling back to a 100ms flush timer when the batch doesn't fill.

Requires: duckdb>=0.10 (Parquet support built-in).

Usage:
    queue = DuckDBWriteQueue("data/ticks.duckdb")
    await queue.start()
    await queue.enqueue("ticks", [{"symbol": "XAUUSD", "bid": 2345.10, ...}])
    ...
    await queue.stop()  # drains remaining records
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import re

import duckdb
import structlog

logger = structlog.get_logger(__name__)

# Defaults
DEFAULT_MAX_QUEUE_SIZE: int = 100_000
DEFAULT_BATCH_SIZE: int = 1_000
DEFAULT_FLUSH_INTERVAL_SEC: float = 0.1  # 100ms

# Table name whitelist — prevents SQL injection via table parameter.
# Add new tables here when needed. Pattern: alphanumeric + underscore only.
_TABLE_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_ALLOWED_TABLES: set[str] = {
    "ticks", "bars", "trades", "signals", "features",
    "order_book", "funding_rates", "sentiment", "ohlcv",
    "shadow_trades",
}


def _validate_table_name(table: str) -> str:
    """Validate table name to prevent SQL injection.

    Checks both regex pattern and whitelist. Returns the validated table
    name if safe, raises ValueError otherwise.
    """
    if not table or not _TABLE_NAME_RE.match(table):
        raise ValueError(f"Invalid table name: {table!r}")
    if table not in _ALLOWED_TABLES:
        raise ValueError(f"Table {table!r} not in allowed whitelist: {_ALLOWED_TABLES}")
    return table


@dataclass
class WriteStats:
    """Cumulative write statistics for monitoring."""

    total_enqueued: int = 0
    total_written: int = 0
    total_flushes: int = 0
    total_errors: int = 0
    last_flush_duration_ms: float = 0.0
    last_flush_record_count: int = 0
    queue_depth: int = 0


class DuckDBWriteQueue:
    """
    Single-writer async queue backed by DuckDB.

    Producers call :meth:`enqueue` from any coroutine. A single background
    ``writer_loop`` drains the queue, batches records, and writes them inside
    a transaction for durability and speed.

    Args:
        db_path: Path to the DuckDB file. Created on first write.
        max_queue_size: Maximum pending records before ``enqueue`` blocks.
        batch_size: Records per bulk INSERT.
        flush_interval: Seconds between forced flushes when batch isn't full.
    """

    def __init__(
        self,
        db_path: str | Path = "data/ticks.duckdb",
        max_queue_size: int = DEFAULT_MAX_QUEUE_SIZE,
        batch_size: int = DEFAULT_BATCH_SIZE,
        flush_interval: float = DEFAULT_FLUSH_INTERVAL_SEC,
    ) -> None:
        self._db_path = str(db_path)
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(
            maxsize=max_queue_size,
        )
        self._conn: Optional[duckdb.DuckDBPyConnection] = None
        self._writer_task: Optional[asyncio.Task[None]] = None
        self._running: bool = False
        self._stats = WriteStats()
        self._dropped_ticks: int = 0  # ponytail: drop counter for overflow monitoring
        self._ensure_parent_dir()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Open the DuckDB connection and start the writer loop."""
        if self._running:
            return
        self._conn = duckdb.connect(self._db_path)
        self._conn.execute("SET enable_progress_bar = false;")
        self._running = True
        self._writer_task = asyncio.create_task(
            self._writer_loop(), name="duckdb_writer",
        )
        logger.info("duckdb_write_queue.started", db_path=self._db_path)

    async def stop(self, drain: bool = True) -> None:
        """
        Stop the writer loop.

        Args:
            drain: If True, flush remaining records before closing.
        """
        if not self._running:
            return
        self._running = False

        if drain:
            await self._drain_remaining()

        if self._writer_task is not None:
            self._writer_task.cancel()
            try:
                await self._writer_task
            except asyncio.CancelledError:
                pass
            self._writer_task = None

        if self._conn is not None:
            self._conn.close()
            self._conn = None

        logger.info(
            "duckdb_write_queue.stopped",
            total_written=self._stats.total_written,
            total_flushes=self._stats.total_flushes,
            total_errors=self._stats.total_errors,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def enqueue(self, table: str, records: Sequence[Dict[str, Any]]) -> None:
        """
        Enqueue records for async write.

        Each record is tagged with its target table. The writer loop batches
        records by table for efficient bulk inserts.

        Drop-oldest policy: When queue is full, drop the oldest record and
        log a warning. This ensures the LATEST tick is always captured,
        which is critical for real-time trading on Monday market open.

        Args:
            table: Target DuckDB table name.
            records: List of dicts. Keys become column names.
        """
        if not self._running:
            raise RuntimeError("DuckDBWriteQueue is not running. Call start() first.")

        for rec in records:
            table_name = _validate_table_name(table)
            rec["_table"] = table_name
            try:
                self._queue.put_nowait(rec)
                self._stats.total_enqueued += 1
            except asyncio.QueueFull:
                # Drop oldest to make room for the latest tick
                try:
                    dropped_rec = self._queue.get_nowait()
                    self._dropped_ticks += 1
                    # ponytail: always log drops — silent data loss is a crime in trading
                    logger.warning(
                        "queue_overflow_drop",
                        dropped_symbol=dropped_rec.get("symbol", "unknown"),
                        dropped_time=dropped_rec.get("timestamp", "unknown"),
                        total_dropped=self._dropped_ticks,
                        queue_size=self._queue.qsize(),
                    )
                    self._queue.put_nowait(rec)
                    self._stats.total_enqueued += 1
                except asyncio.QueueEmpty:
                    # Race condition: queue was full but drained between put and get
                    try:
                        self._queue.put_nowait(rec)
                        self._stats.total_enqueued += 1
                    except asyncio.QueueFull:
                        self._dropped_ticks += 1
                        logger.warning("queue_overflow_drop_newest", total_dropped=self._dropped_ticks)

        self._stats.queue_depth = self._queue.qsize()

    @property
    def stats(self) -> WriteStats:
        """Current write statistics (read-only snapshot)."""
        self._stats.queue_depth = self._queue.qsize()
        return self._stats

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Writer loop
    # ------------------------------------------------------------------

    async def _writer_loop(self) -> None:
        """
        Background coroutine that drains the queue.

        Flushes when either:
        - ``batch_size`` records are accumulated, or
        - ``flush_interval`` seconds elapse since the last flush.
        """
        while self._running:
            try:
                first = await self._wait_for_first()
                if first is not None:
                    batch = [first] + self._drain_up_to(self._batch_size - 1)
                    self._write_batch(batch)
                else:
                    # Timer fired with empty queue — check for partial batch
                    batch = self._drain_up_to(self._batch_size)
                    if batch:
                        self._write_batch(batch)
            except asyncio.CancelledError:
                break
            except Exception:
                self._stats.total_errors += 1
                logger.exception("duckdb_write_queue.writer_error")

    async def _wait_for_first(self) -> Optional[Dict[str, Any]]:
        """Block until at least one record is available or flush timer fires."""
        try:
            return await asyncio.wait_for(
                self._queue.get(), timeout=self._flush_interval,
            )
        except asyncio.TimeoutError:
            return None

    def _drain_up_to(self, limit: int) -> List[Dict[str, Any]]:
        """Drain up to *limit* items from the queue (non-blocking)."""
        batch: List[Dict[str, Any]] = []
        while len(batch) < limit:
            try:
                batch.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return batch

    # ------------------------------------------------------------------
    # DuckDB writes
    # ------------------------------------------------------------------

    def _write_batch(self, batch: List[Dict[str, Any]]) -> None:
        """Insert a batch of records grouped by table inside a transaction."""
        if not batch or self._conn is None:
            return

        t0 = time.perf_counter()
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for rec in batch:
            table = rec.pop("_table", "unknown")
            grouped.setdefault(table, []).append(rec)

        try:
            self._conn.execute("BEGIN TRANSACTION;")
            for table, rows in grouped.items():
                if not rows:
                    continue
                self._ensure_table(table, rows[0])
                columns = list(rows[0].keys())
                placeholders = ", ".join(["?"] * len(columns))
                col_names = ", ".join(columns)
                safe_table = _validate_table_name(table)
                sql = f"INSERT INTO {safe_table} ({col_names}) VALUES ({placeholders})"
                values = [list(row.values()) for row in rows]
                self._conn.executemany(sql, values)
            self._conn.execute("COMMIT;")

            elapsed_ms = (time.perf_counter() - t0) * 1000
            self._stats.total_written += len(batch)
            self._stats.total_flushes += 1
            self._stats.last_flush_duration_ms = elapsed_ms
            self._stats.last_flush_record_count = len(batch)

            logger.debug(
                "duckdb_write_queue.flush",
                records=len(batch),
                tables=list(grouped.keys()),
                duration_ms=round(elapsed_ms, 2),
            )
        except Exception:
            self._conn.execute("ROLLBACK;")
            raise

    def _ensure_table(self, table: str, sample: Dict[str, Any]) -> None:
        """Create table if it doesn't exist, inferring columns from sample."""
        if self._conn is None:
            return
        # Check if table exists
        exists = self._conn.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
            [table],
        ).fetchone()
        if exists and exists[0] > 0:
            return

        col_defs = []
        for col_name, value in sample.items():
            if isinstance(value, bool):
                dtype = "BOOLEAN"
            elif isinstance(value, int):
                dtype = "BIGINT"
            elif isinstance(value, float):
                dtype = "DOUBLE"
            else:
                dtype = "VARCHAR"
            col_defs.append(f"{col_name} {dtype}")

        create_sql = f"CREATE TABLE IF NOT EXISTS {_validate_table_name(table)} ({', '.join(col_defs)});"
        self._conn.execute(create_sql)
        logger.info("duckdb_write_queue.table_created", table=table, columns=len(col_defs))

    def _ensure_parent_dir(self) -> None:
        """Create parent directories for the DuckDB file."""
        parent = Path(self._db_path).parent
        if parent and not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)

    async def _drain_remaining(self) -> None:
        """Flush all remaining records in the queue."""
        remaining = self._drain_up_to(self._queue.maxsize or DEFAULT_MAX_QUEUE_SIZE)
        if remaining:
            self._write_batch(remaining)
            logger.info("duckdb_write_queue.drained", records=len(remaining))

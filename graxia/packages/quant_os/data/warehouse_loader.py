"""DuckDB-backed warehouse loader.

Wires DuckDB to:
- Parquet files in data/warehouse/ohlcv/ and data/warehouse/ticks/ (hive-partitioned)
- The central quantos.duckdb at data/warehouse/quantos.duckdb

Usage:
    from data.warehouse_loader import Warehouse
    wh = Warehouse()
    df = wh.get_ohlcv("XAUUSD", "M15", start="2026-05-01", end="2026-05-31")
    wh.close()
"""

from __future__ import annotations

import contextlib
import json
import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

# SQL identifier safety: we use parameterized queries for VALUES, but column / table
# names must still go through a regex check. We allow only alphanumeric + underscore.
_SQL_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_ident(name: str) -> str:
    """Return a SQL-safe identifier or raise ValueError."""
    if not name or not _SQL_IDENT_RE.match(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return name


def _to_ts(value: str | datetime | date | None) -> str | None:
    """Coerce a date-ish input to an ISO-8601 string DuckDB can parse."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _scalar(cur: Any) -> Any:
    """First column of the first row, or raise.

    `.fetchone()` returns None when a query yields no rows; the previous code
    indexed the result directly, which raised an opaque TypeError instead of
    saying which query came back empty.
    """
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("query returned no rows where exactly one was expected")
    return row[0]


class Warehouse:
    """DuckDB-backed warehouse for OHLCV/ticks/orders.

    Single process, thread-safe via lock. Opens the warehouse database in
    read-write mode and creates it (along with required tables) on first use.
    """

    def __init__(self, db_path: str | Path = "data/warehouse/quantos.duckdb") -> None:
        """Open DuckDB connection. Creates file if not exists."""
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn: duckdb.DuckDBPyConnection = duckdb.connect(str(self._db_path))
        # Enable hive-partitioned parquet reads if supported.
        # older/newer DuckDB versions may not need (or accept) this
        with contextlib.suppress(Exception):
            self._conn.execute("SET enable_hive_partitioning = true;")
        self._init_schema()

    # ── Internal helpers ──────────────────────────────────────────
    def _init_schema(self) -> None:
        """Create orders / fills / manifests tables if they don't exist."""
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id              BIGINT PRIMARY KEY,
                    client_order_id VARCHAR,
                    symbol          VARCHAR,
                    side            VARCHAR,
                    order_type      VARCHAR,
                    quantity        DOUBLE,
                    price           DOUBLE,
                    status          VARCHAR,
                    strategy_id     VARCHAR,
                    created_at      TIMESTAMP,
                    raw             JSON
                );
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS fills (
                    id           BIGINT PRIMARY KEY,
                    order_id     BIGINT,
                    symbol       VARCHAR,
                    side         VARCHAR,
                    quantity     DOUBLE,
                    price        DOUBLE,
                    fee          DOUBLE,
                    strategy_id  VARCHAR,
                    filled_at    TIMESTAMP,
                    raw          JSON
                );
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS manifests (
                    file_path    VARCHAR PRIMARY KEY,
                    symbol       VARCHAR,
                    date_range   VARCHAR,
                    row_count    BIGINT,
                    checksum     VARCHAR,
                    schema_hash  VARCHAR,
                    pipeline_version VARCHAR,
                    created_at   VARCHAR,
                    raw          JSON
                );
                """
            )
            # Auto-increment sequences for orders/fills.
            self._conn.execute("CREATE SEQUENCE IF NOT EXISTS orders_seq START 1;")
            self._conn.execute("CREATE SEQUENCE IF NOT EXISTS fills_seq START 1;")

    # _execute() used to live here: it took the lock, executed, and returned the
    # shared connection -- releasing the lock before the caller fetched. Every
    # read then raced. Deleted rather than documented, so the shape cannot be
    # reached for again; _query_df / _query_all below hold the lock across
    # execute AND fetch. Writers keep using self._conn.execute directly inside
    # their own `with self._lock` blocks, which was always correct.

    def _query_df(self, sql: str, params: list[Any] | None = None) -> pd.DataFrame:
        """Execute and materialise to a DataFrame with the lock held throughout.

        DuckDB gives every `execute()` on a connection the same cursor, so
        execute-then-fetch is only atomic if nothing else touches the
        connection in between. Splitting the two across the lock boundary let
        four reader threads interleave and read each other's result sets.
        """
        with self._lock:
            cur = self._conn.execute(sql) if params is None else self._conn.execute(sql, params)
            try:
                return cur.df()
            except duckdb.Error:
                return pd.DataFrame()

    def _query_all(self, sql: str, params: list[Any] | None = None) -> list[Any]:
        """Execute and fetch all rows with the lock held throughout."""
        with self._lock:
            cur = self._conn.execute(sql) if params is None else self._conn.execute(sql, params)
            return cur.fetchall()

    def _view_name(self, kind: str, symbol: str, frequency: str | None = None) -> str:
        """Build a deterministic view name from inputs."""
        sym = _safe_ident(symbol)
        if frequency is not None:
            freq = _safe_ident(frequency)
            return f"v_{kind}_{sym}_{freq}"
        return f"v_{kind}_{sym}"

    def _has_files(self, glob_pattern: str) -> bool:
        """True if at least one file matches a hive-partitioned parquet glob."""
        # DuckDB's read_parquet returns an error on empty globs; probe via glob.
        # We resolve the partition prefix to a real directory and look for parquet.
        from glob import glob

        matches = glob(glob_pattern)
        return len(matches) > 0

    # ── OHLCV ─────────────────────────────────────────────────────
    def register_ohlcv_glob(self, symbol: str, frequency: str) -> None:
        """Register all ohlcv parquet files for a symbol/freq as a DuckDB view.

        Uses the hive-partitioned layout under data/warehouse/ohlcv/. The
        ``symbol`` and ``frequency`` partitions are automatically exposed as
        columns by DuckDB when ``hive_partitioning`` is on.
        """
        view = self._view_name("ohlcv", symbol, frequency)
        # Sanitize inputs used in the SQL string.
        sym = _safe_ident(symbol)
        freq = _safe_ident(frequency)
        root = self._db_path.parent / "ohlcv"
        glob_pattern = str(root / f"symbol={sym}" / f"frequency={freq}" / "**" / "*.parquet")
        # Use forward slashes for DuckDB glob.
        glob_sql = glob_pattern.replace("\\", "/")
        sql = f"CREATE OR REPLACE VIEW {view} AS SELECT * FROM read_parquet('{glob_sql}')"
        with self._lock:
            self._conn.execute(sql)

    def get_ohlcv(
        self,
        symbol: str,
        frequency: str,
        start: str | datetime | date | None = None,
        end: str | datetime | date | None = None,
        columns: list[str] | None = None,
    ) -> pd.DataFrame:
        """Query OHLCV data for a symbol/frequency within a date range.

        Uses the registered glob view for efficient columnar reads. Returns
        an empty DataFrame if no data is registered for the symbol/frequency
        or no rows match the date filter.
        """
        view = self._view_name("ohlcv", symbol, frequency)
        # Probe for view existence.
        with self._lock:
            exists = _scalar(self._conn.execute("SELECT count(*) FROM duckdb_views WHERE view_name = ?", [view]))
        if not exists:
            return pd.DataFrame()

        # Column list
        if columns:
            # Validate identifiers and keep order.
            safe_cols = [_safe_ident(c) for c in columns]
            col_sql = ", ".join(safe_cols)
        else:
            col_sql = "*"

        where: list[str] = []
        params: list[Any] = []
        start_s = _to_ts(start)
        end_s = _to_ts(end)
        if start_s is not None:
            where.append("time >= ?")
            params.append(start_s)
        if end_s is not None:
            where.append("time <= ?")
            params.append(end_s)
        where_sql = (" WHERE " + " AND ".join(where)) if where else ""

        sql = f"SELECT {col_sql} FROM {view}{where_sql} ORDER BY time"
        return self._query_df(sql, params)

    # ── Ticks ─────────────────────────────────────────────────────
    def register_ticks_glob(self, symbol: str) -> None:
        """Register all tick parquet files for a symbol as a view."""
        view = self._view_name("ticks", symbol)
        sym = _safe_ident(symbol)
        root = self._db_path.parent / "ticks"
        glob_pattern = str(root / f"symbol={sym}" / "**" / "*.parquet")
        glob_sql = glob_pattern.replace("\\", "/")
        sql = f"CREATE OR REPLACE VIEW {view} AS SELECT * FROM read_parquet('{glob_sql}')"
        with self._lock:
            self._conn.execute(sql)

    def get_ticks(
        self,
        symbol: str,
        start: str | datetime | date | None = None,
        end: str | datetime | date | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        """Query ticks for a symbol with optional date range and row limit."""
        view = self._view_name("ticks", symbol)
        with self._lock:
            exists = _scalar(self._conn.execute("SELECT count(*) FROM duckdb_views WHERE view_name = ?", [view]))
        if not exists:
            return pd.DataFrame()

        where: list[str] = []
        params: list[Any] = []
        start_s = _to_ts(start)
        end_s = _to_ts(end)
        if start_s is not None:
            where.append("time >= ?")
            params.append(start_s)
        if end_s is not None:
            where.append("time <= ?")
            params.append(end_s)
        where_sql = (" WHERE " + " AND ".join(where)) if where else ""

        limit_sql = ""
        if limit is not None and limit > 0:
            limit_sql = f" LIMIT {int(limit)}"

        sql = f"SELECT * FROM {view}{where_sql} ORDER BY time{limit_sql}"
        return self._query_df(sql, params)

    # ── Orders / Fills ────────────────────────────────────────────
    def insert_order(self, order: dict) -> int:
        """Insert one order row, return the assigned row id."""
        if not isinstance(order, dict):
            raise TypeError("order must be a dict")
        # Assign a sequential id (override-able).
        with self._lock:
            row_id = _scalar(self._conn.execute("SELECT nextval('orders_seq')"))
            self._conn.execute(
                """
                INSERT INTO orders
                    (id, client_order_id, symbol, side, order_type,
                     quantity, price, status, strategy_id, created_at, raw)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    order.get("id", row_id),
                    order.get("client_order_id"),
                    order.get("symbol"),
                    order.get("side"),
                    order.get("order_type"),
                    float(order["quantity"]) if order.get("quantity") is not None else None,
                    float(order["price"]) if order.get("price") is not None else None,
                    order.get("status", "CREATED"),
                    order.get("strategy_id"),
                    order.get("created_at"),
                    json.dumps(order, default=str),
                ],
            )
            return int(order.get("id", row_id))

    def insert_fill(self, fill: dict) -> int:
        """Insert one fill row, return the assigned row id."""
        if not isinstance(fill, dict):
            raise TypeError("fill must be a dict")
        with self._lock:
            row_id = _scalar(self._conn.execute("SELECT nextval('fills_seq')"))
            self._conn.execute(
                """
                INSERT INTO fills
                    (id, order_id, symbol, side, quantity, price, fee,
                     strategy_id, filled_at, raw)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    fill.get("id", row_id),
                    fill.get("order_id"),
                    fill.get("symbol"),
                    fill.get("side"),
                    float(fill["quantity"]) if fill.get("quantity") is not None else None,
                    float(fill["price"]) if fill.get("price") is not None else None,
                    float(fill.get("fee", 0.0) or 0.0),
                    fill.get("strategy_id"),
                    fill.get("filled_at"),
                    json.dumps(fill, default=str),
                ],
            )
            return int(fill.get("id", row_id))

    def list_orders(self, symbol: str | None = None, limit: int = 1000) -> pd.DataFrame:
        """Return recent orders, newest first. Filter by ``symbol`` if given."""
        where = ""
        params: list[Any] = []
        if symbol:
            where = " WHERE symbol = ?"
            params = [symbol]
        sql = f"SELECT * FROM orders{where} ORDER BY created_at DESC LIMIT {int(limit)}"
        return self._query_df(sql, params)

    # ── Manifests ─────────────────────────────────────────────────
    def list_manifests(self, symbol: str | None = None) -> pd.DataFrame:
        """Return all stored manifests, optionally filtered by symbol."""
        if symbol:
            return self._query_df(
                "SELECT * FROM manifests WHERE symbol = ? ORDER BY created_at DESC",
                [symbol],
            )
        return self._query_df("SELECT * FROM manifests ORDER BY created_at DESC")

    def get_manifest(self, file_path: str) -> dict | None:
        """Return a single manifest dict by ``file_path`` or None if missing."""
        rows = self._query_all("SELECT raw FROM manifests WHERE file_path = ?", [file_path])
        if not rows:
            return None
        raw = rows[0][0]
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return {"raw": raw}

    def upsert_manifest(self, file_path: str, manifest: dict) -> None:
        """Store or replace a manifest for a file path."""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO manifests
                    (file_path, symbol, date_range, row_count, checksum,
                     schema_hash, pipeline_version, created_at, raw)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (file_path) DO UPDATE SET
                    symbol = excluded.symbol,
                    date_range = excluded.date_range,
                    row_count = excluded.row_count,
                    checksum = excluded.checksum,
                    schema_hash = excluded.schema_hash,
                    pipeline_version = excluded.pipeline_version,
                    created_at = excluded.created_at,
                    raw = excluded.raw
                """,
                [
                    file_path,
                    manifest.get("symbol"),
                    manifest.get("date_range"),
                    int(manifest.get("row_count", 0) or 0),
                    manifest.get("checksum"),
                    manifest.get("schema_hash"),
                    manifest.get("pipeline_version"),
                    manifest.get("created_at"),
                    json.dumps(manifest, default=str),
                ],
            )

    # ── Stats / Maintenance ───────────────────────────────────────
    def stats(self) -> dict[str, Any]:
        """Return row counts for all known warehouse tables."""
        out: dict[str, Any] = {"db_path": str(self._db_path)}
        with self._lock:
            tables = [
                r[0]
                for r in self._conn.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'main' AND table_type = 'BASE TABLE'"
                ).fetchall()
            ]
            for t in tables:
                count = _scalar(self._conn.execute(f"SELECT count(*) FROM {_safe_ident(t)}"))
                out[t] = int(count)
        return out

    def vacuum(self) -> None:
        """Reclaim storage and optimize the warehouse file."""
        with self._lock:
            self._conn.execute("VACUUM;")

    def close(self) -> None:
        """Close the underlying DuckDB connection."""
        with self._lock:
            try:
                if self._conn is not None:
                    self._conn.close()
            finally:
                self._conn = None  # type: ignore[assignment]

    @contextmanager
    def transaction(self) -> Iterator[duckdb.DuckDBPyConnection]:
        """Context manager for an explicit transaction.

        Commits on clean exit, rolls back on any exception.
        """
        with self._lock:
            self._conn.execute("BEGIN TRANSACTION;")
            try:
                yield self._conn
                self._conn.execute("COMMIT;")
            except BaseException:
                self._conn.execute("ROLLBACK;")
                raise

    # Dunder
    def __enter__(self) -> Warehouse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

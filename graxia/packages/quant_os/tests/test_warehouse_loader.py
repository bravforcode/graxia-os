"""Tests for data.warehouse_loader — DuckDB-backed warehouse."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pytest

from graxia.packages.quant_os.data.warehouse_loader import Warehouse

# quant_os package root: <repo>/tests/test_warehouse_loader.py -> <repo>/
REPO_ROOT = Path(__file__).resolve().parent.parent


def _write_ohlcv_parquet(path: Path, times: list[str], close: list[float]) -> None:
    """Write a small OHLCV parquet to ``path`` with a 'time' column."""
    import pyarrow.parquet as pq

    table = pa.table(
        {
            "time": pa.array(times, type=pa.string()),
            "open": pa.array(close, type=pa.float64()),
            "high": pa.array([c + 1.0 for c in close], type=pa.float64()),
            "low": pa.array([c - 1.0 for c in close], type=pa.float64()),
            "close": pa.array(close, type=pa.float64()),
            "volume": pa.array([100] * len(close), type=pa.int64()),
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, str(path))


def _has_real_warehouse_ohlcv() -> bool:
    """True if real XAUUSD M15 ohlcv parquet files exist in the warehouse."""
    base = REPO_ROOT / "data" / "warehouse" / "ohlcv" / "symbol=XAUUSD" / "frequency=M15"
    if not base.exists():
        return False
    return any(base.rglob("*.parquet"))


class TestWarehouseInit:
    def test_warehouse_init_creates_db(self, tmp_path: Path):
        """Fresh db_path is created on init."""
        db = tmp_path / "fresh.duckdb"
        wh = Warehouse(db_path=db)
        try:
            assert db.exists()
            # Tables should exist immediately.
            tables = wh._conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main' AND table_type = 'BASE TABLE'"
            ).fetchall()
            table_names = {t[0] for t in tables}
            assert {"orders", "fills", "manifests"}.issubset(table_names)
        finally:
            wh.close()


class TestWarehouseOhlcv:
    def test_warehouse_get_ohlcv_empty(self, tmp_path: Path):
        """When no view is registered for a symbol/freq, returns empty DataFrame."""
        wh = Warehouse(db_path=tmp_path / "wh.duckdb")
        try:
            df = wh.get_ohlcv("NOSYMBOL", "NOFREQ")
            assert isinstance(df, pd.DataFrame)
            assert df.empty
        finally:
            wh.close()

    def test_warehouse_get_ohlcv_with_synthetic_data(self, tmp_path: Path):
        """Registering a glob and querying returns the synthesized rows."""
        # Build hive layout: <tmp>/ohlcv/symbol=FOO/frequency=M15/source=TEST/year=2026/month=01/x.parquet
        ohlcv_root = tmp_path / "ohlcv"
        part_dir = ohlcv_root / "symbol=FOO" / "frequency=M15" / "source=TEST" / "year=2026" / "month=01"
        part_dir.mkdir(parents=True)
        f = part_dir / "x.parquet"
        _write_ohlcv_parquet(
            f,
            times=[
                "2026-01-01 00:00:00",
                "2026-01-01 00:15:00",
                "2026-01-01 00:30:00",
                "2026-01-01 00:45:00",
            ],
            close=[100.0, 101.0, 102.0, 103.0],
        )

        wh = Warehouse(db_path=tmp_path / "wh.duckdb")
        try:
            wh.register_ohlcv_glob("FOO", "M15")
            df = wh.get_ohlcv("FOO", "M15")
            assert len(df) == 4
            assert "close" in df.columns
            assert df["close"].iloc[0] == 100.0

            # Date-range filter narrows results.
            df2 = wh.get_ohlcv(
                "FOO",
                "M15",
                start="2026-01-01 00:15:00",
                end="2026-01-01 00:30:00",
            )
            assert len(df2) == 2
        finally:
            wh.close()

    def test_warehouse_get_ohlcv_with_real_data(self, tmp_path: Path):
        """Skip if no real warehouse data; otherwise read it back."""
        if not _has_real_warehouse_ohlcv():
            pytest.skip("No real XAUUSD/M15 ohlcv data in data/warehouse/")

        # Use the actual warehouse DB for real data test
        wh = Warehouse(db_path=REPO_ROOT / "data" / "warehouse" / "quantos.duckdb")
        try:
            wh.register_ohlcv_glob("XAUUSD", "M15")
            df = wh.get_ohlcv("XAUUSD", "M15")
            assert not df.empty
            # Required columns should be present.
            assert "time" in df.columns
            assert "close" in df.columns
        finally:
            wh.close()


class TestWarehouseOrders:
    def test_warehouse_insert_and_list_orders(self, tmp_path: Path):
        """Insert a few orders and round-trip them via list_orders."""
        wh = Warehouse(db_path=tmp_path / "wh.duckdb")
        try:
            wh.insert_order(
                {
                    "client_order_id": "co-1",
                    "symbol": "XAUUSD",
                    "side": "BUY",
                    "order_type": "MARKET",
                    "quantity": 1.5,
                    "price": 2400.0,
                    "status": "CREATED",
                    "strategy_id": "tsm_v1",
                    "created_at": datetime(2024, 6, 1, 12, 0, tzinfo=UTC),
                }
            )
            wh.insert_order(
                {
                    "client_order_id": "co-2",
                    "symbol": "EURUSD",
                    "side": "SELL",
                    "order_type": "LIMIT",
                    "quantity": 0.5,
                    "price": 1.085,
                    "status": "FILLED",
                    "strategy_id": "tsm_v1",
                    "created_at": datetime(2024, 6, 2, 9, 0, tzinfo=UTC),
                }
            )

            df = wh.list_orders()
            assert len(df) == 2
            # Most recent first.
            assert df.iloc[0]["client_order_id"] == "co-2"

            xau = wh.list_orders(symbol="XAUUSD")
            assert len(xau) == 1
            assert xau.iloc[0]["symbol"] == "XAUUSD"
        finally:
            wh.close()

    def test_warehouse_insert_fill(self, tmp_path: Path):
        """Insert a fill row and read it back."""
        wh = Warehouse(db_path=tmp_path / "wh.duckdb")
        try:
            oid = wh.insert_order(
                {
                    "client_order_id": "of-1",
                    "symbol": "XAUUSD",
                    "side": "BUY",
                    "order_type": "MARKET",
                    "quantity": 1.0,
                    "price": 2400.0,
                    "strategy_id": "tsm_v1",
                    "created_at": datetime(2024, 6, 1, 12, 0, tzinfo=UTC),
                }
            )
            fid = wh.insert_fill(
                {
                    "order_id": oid,
                    "symbol": "XAUUSD",
                    "side": "BUY",
                    "quantity": 1.0,
                    "price": 2400.5,
                    "fee": 0.5,
                    "strategy_id": "tsm_v1",
                    "filled_at": datetime(2024, 6, 1, 12, 1, tzinfo=UTC),
                }
            )
            assert isinstance(fid, int)
            # Fills are stored, can be queried via duckdb directly.
            count = wh._conn.execute("SELECT count(*) FROM fills").fetchone()[0]
            assert count == 1
        finally:
            wh.close()


class TestWarehouseStats:
    def test_warehouse_stats(self, tmp_path: Path):
        """stats() returns row counts for the known tables."""
        wh = Warehouse(db_path=tmp_path / "wh.duckdb")
        try:
            wh.insert_order(
                {
                    "client_order_id": "s-1",
                    "symbol": "XAUUSD",
                    "side": "BUY",
                    "order_type": "MARKET",
                    "quantity": 1.0,
                    "price": 100.0,
                    "strategy_id": "x",
                    "created_at": datetime(2024, 1, 1, tzinfo=UTC),
                }
            )
            stats = wh.stats()
            assert isinstance(stats, dict)
            assert stats["db_path"].endswith("wh.duckdb")
            assert stats["orders"] == 1
            assert stats["fills"] == 0
            assert "manifests" in stats
        finally:
            wh.close()


class TestWarehouseConcurrency:
    def test_warehouse_concurrent_reads(self, tmp_path: Path):
        """Multiple threads reading the same view should all get results."""
        # Synthesize a tiny dataset.
        ohlcv_root = tmp_path / "ohlcv"
        part_dir = ohlcv_root / "symbol=ETH" / "frequency=M15" / "source=TEST" / "year=2026" / "month=01"
        part_dir.mkdir(parents=True)
        f = part_dir / "x.parquet"
        _write_ohlcv_parquet(
            f,
            times=[f"2026-01-01 00:{m:02d}:00" for m in range(0, 60, 15)],
            close=[float(i) for i in range(4)],
        )

        wh = Warehouse(db_path=tmp_path / "wh.duckdb")
        try:
            wh.register_ohlcv_glob("ETH", "M15")

            results: list[int] = []
            errors: list[BaseException] = []
            lock = threading.Lock()

            def worker():
                try:
                    df = wh.get_ohlcv("ETH", "M15")
                    with lock:
                        results.append(len(df))
                except BaseException as e:  # noqa: BLE001
                    with lock:
                        errors.append(e)

            threads = [threading.Thread(target=worker) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)
            assert not errors, f"thread errors: {errors}"
            assert len(results) == 4
            for r in results:
                assert r == 4
        finally:
            wh.close()


class TestWarehouseTransaction:
    def test_warehouse_transaction_rollback(self, tmp_path: Path):
        """An exception inside the transaction context rolls back the change."""
        wh = Warehouse(db_path=tmp_path / "wh.duckdb")
        try:
            with pytest.raises(RuntimeError, match="boom"):
                with wh.transaction() as conn:
                    conn.execute(
                        "INSERT INTO orders "
                        "(id, client_order_id, symbol, side, order_type, "
                        "quantity, price, status, strategy_id, created_at, raw) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        [
                            999,
                            "rb-1",
                            "XAUUSD",
                            "BUY",
                            "MARKET",
                            1.0,
                            100.0,
                            "CREATED",
                            "x",
                            datetime(2024, 1, 1, tzinfo=UTC),
                            "{}",
                        ],
                    )
                    raise RuntimeError("boom")
            # Row must NOT be visible after rollback.
            count = wh._conn.execute("SELECT count(*) FROM orders WHERE client_order_id = 'rb-1'").fetchone()[0]
            assert count == 0
        finally:
            wh.close()

    def test_warehouse_transaction_commit(self, tmp_path: Path):
        """A clean transaction commits its writes."""
        wh = Warehouse(db_path=tmp_path / "wh.duckdb")
        try:
            with wh.transaction() as conn:
                conn.execute(
                    "INSERT INTO orders "
                    "(id, client_order_id, symbol, side, order_type, "
                    "quantity, price, status, strategy_id, created_at, raw) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        1000,
                        "ok-1",
                        "XAUUSD",
                        "BUY",
                        "MARKET",
                        1.0,
                        100.0,
                        "CREATED",
                        "x",
                        datetime(2024, 1, 1, tzinfo=UTC),
                        "{}",
                    ],
                )
            count = wh._conn.execute("SELECT count(*) FROM orders WHERE client_order_id = 'ok-1'").fetchone()[0]
            assert count == 1
        finally:
            wh.close()


class TestWarehouseClose:
    def test_warehouse_close(self, tmp_path: Path):
        """close() is idempotent and leaves the file intact."""
        wh = Warehouse(db_path=tmp_path / "wh.duckdb")
        wh.insert_order(
            {
                "client_order_id": "c-1",
                "symbol": "XAUUSD",
                "side": "BUY",
                "order_type": "MARKET",
                "quantity": 1.0,
                "price": 100.0,
                "strategy_id": "x",
                "created_at": datetime(2024, 1, 1, tzinfo=UTC),
            }
        )
        wh.close()
        # Calling close() again should not raise.
        wh.close()
        # Re-open the same file and confirm the row persisted.
        wh2 = Warehouse(db_path=tmp_path / "wh.duckdb")
        try:
            count = wh2._conn.execute("SELECT count(*) FROM orders").fetchone()[0]
            assert count == 1
        finally:
            wh2.close()

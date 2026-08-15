"""Tests for data/state_db.py — SQLite state persistence."""

from __future__ import annotations

import concurrent.futures
import sqlite3
from pathlib import Path

import pytest

from graxia.packages.quant_os.data.state_db import AccountState, Order, Position, StateDB

# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture()
def db(tmp_path: Path) -> StateDB:
    """Create an isolated StateDB in a temp directory."""
    db = StateDB(tmp_path / "test_state.db")
    yield db
    db.close()


# ======================================================================
# Schema
# ======================================================================


class TestSchema:
    def test_init_creates_tables(self, db: StateDB) -> None:
        """All 5 tables should exist after init."""
        stats = db.stats()
        assert "orders" in stats
        assert "positions" in stats
        assert "account_state" in stats
        assert "circuit_breakers" in stats
        assert stats["schema_version"] == 1

    def test_init_creates_file(self, tmp_path: Path) -> None:
        """Database file should be created."""
        p = tmp_path / "sub" / "test.db"
        db = StateDB(p)
        assert p.exists()
        db.close()


# ======================================================================
# Orders
# ======================================================================


class TestOrders:
    def test_insert_and_get_order(self, db: StateDB) -> None:
        """Round trip: insert → get."""
        order = Order(order_id="ORD-001", symbol="XAUUSD", side="BUY", volume=0.01)
        db.insert_order(order)
        got = db.get_order("ORD-001")
        assert got is not None
        assert got.symbol == "XAUUSD"
        assert got.side == "BUY"
        assert got.volume == 0.01
        assert got.status == "PENDING"

    def test_update_order_status(self, db: StateDB) -> None:
        """Status change from PENDING → FILLED with filled_price."""
        order = Order(order_id="ORD-002", symbol="EURUSD", side="SELL", volume=0.1)
        db.insert_order(order)
        db.update_order_status("ORD-002", "FILLED", filled_price=1.0850)
        got = db.get_order("ORD-002")
        assert got is not None
        assert got.status == "FILLED"
        assert got.filled_price == 1.0850

    def test_unique_client_tag_idempotency(self, db: StateDB) -> None:
        """Duplicate client_tag should raise IntegrityError."""
        o1 = Order(order_id="A1", symbol="XAUUSD", side="BUY", volume=0.01, client_tag="TAG-1")
        o2 = Order(order_id="A2", symbol="XAUUSD", side="BUY", volume=0.01, client_tag="TAG-1")
        db.insert_order(o1)
        with pytest.raises(sqlite3.IntegrityError):
            db.insert_order(o2)

    def test_list_open_orders_excludes_terminal(self, db: StateDB) -> None:
        """Only non-terminal orders should appear."""
        db.insert_order(Order(order_id="O1", symbol="XAUUSD", side="BUY", volume=0.01, status="PENDING"))
        db.insert_order(Order(order_id="O2", symbol="XAUUSD", side="BUY", volume=0.01, status="FILLED"))
        db.insert_order(Order(order_id="O3", symbol="XAUUSD", side="BUY", volume=0.01, status="CANCELLED"))
        db.insert_order(Order(order_id="O4", symbol="EURUSD", side="SELL", volume=0.1, status="SENT_TO_BROKER"))
        open_orders = db.list_open_orders()
        ids = {o.order_id for o in open_orders}
        assert "O1" in ids
        assert "O4" in ids
        assert "O2" not in ids
        assert "O3" not in ids

    def test_list_orders_by_date_range(self, db: StateDB) -> None:
        """Date range filtering works."""
        db.insert_order(
            Order(order_id="D1", symbol="XAUUSD", side="BUY", volume=0.01, created_at="2024-01-15T10:00:00")
        )
        db.insert_order(
            Order(order_id="D2", symbol="XAUUSD", side="BUY", volume=0.01, created_at="2024-06-15T10:00:00")
        )
        db.insert_order(
            Order(order_id="D3", symbol="XAUUSD", side="BUY", volume=0.01, created_at="2025-01-15T10:00:00")
        )
        result = db.list_orders_by_date_range("2024-01-01", "2024-12-31")
        ids = {o.order_id for o in result}
        assert ids == {"D1", "D2"}

    def test_get_order_not_found(self, db: StateDB) -> None:
        """Non-existent order returns None."""
        assert db.get_order("NOPE") is None


# ======================================================================
# Positions
# ======================================================================


class TestPositions:
    def test_upsert_position_creates(self, db: StateDB) -> None:
        """First insert creates position."""
        pos = Position(symbol="XAUUSD", side="LONG", volume=0.01, avg_entry_price=2350.0)
        db.upsert_position(pos)
        got = db.get_position("XAUUSD")
        assert got is not None
        assert got.side == "LONG"
        assert got.volume == 0.01

    def test_upsert_position_updates(self, db: StateDB) -> None:
        """Second insert updates existing position."""
        db.upsert_position(Position(symbol="XAUUSD", side="LONG", volume=0.01, avg_entry_price=2350.0))
        db.upsert_position(Position(symbol="XAUUSD", side="LONG", volume=0.02, avg_entry_price=2360.0))
        got = db.get_position("XAUUSD")
        assert got is not None
        assert got.volume == 0.02
        assert got.avg_entry_price == 2360.0

    def test_close_position_marks_zero(self, db: StateDB) -> None:
        """Close sets volume=0, side=FLAT."""
        db.upsert_position(Position(symbol="EURUSD", side="LONG", volume=0.1, avg_entry_price=1.08))
        db.close_position("EURUSD", 1.09)
        got = db.get_position("EURUSD")
        assert got is not None
        assert got.side == "FLAT"
        assert got.volume == 0

    def test_list_positions(self, db: StateDB) -> None:
        """All positions returned."""
        db.upsert_position(Position(symbol="A", side="LONG", volume=0.01, avg_entry_price=100))
        db.upsert_position(Position(symbol="B", side="SHORT", volume=0.02, avg_entry_price=200))
        result = db.list_positions()
        symbols = {p.symbol for p in result}
        assert symbols == {"A", "B"}


# ======================================================================
# Account
# ======================================================================


class TestAccount:
    def test_get_account_default(self, db: StateDB) -> None:
        """Returns defaults when no row exists."""
        acc = db.get_account()
        assert acc.balance == 0.0
        assert acc.equity == 0.0
        assert acc.currency == "USD"

    def test_update_and_get_account(self, db: StateDB) -> None:
        """Round trip: update → get."""
        db.update_account(AccountState(balance=10000, equity=10000, margin_used=500))
        got = db.get_account()
        assert got.balance == 10000
        assert got.equity == 10000
        assert got.margin_used == 500

    def test_account_singleton_constraint(self, db: StateDB) -> None:
        """Only id=1 allowed — direct INSERT with id=2 should fail."""
        with pytest.raises(sqlite3.IntegrityError):
            db._conn.execute(
                "INSERT INTO account_state (id, balance, equity, updated_at) VALUES (2, 0, 0, '2024-01-01')"
            )


# ======================================================================
# Circuit Breakers
# ======================================================================


class TestCircuitBreakers:
    def test_trip_and_list_active(self, db: StateDB) -> None:
        """Trip a breaker and verify it appears in active list."""
        db.trip_breaker("daily_loss", "exceeded 5% limit")
        active = db.list_active_breakers()
        assert len(active) == 1
        assert active[0].name == "daily_loss"
        assert active[0].active is True
        assert active[0].reason == "exceeded 5% limit"

    def test_reset_breaker(self, db: StateDB) -> None:
        """Reset a tripped breaker."""
        db.trip_breaker("drawdown", "peak drawdown")
        db.reset_breaker("drawdown")
        active = db.list_active_breakers()
        assert len(active) == 0

    def test_trip_breaker_updates_reason(self, db: StateDB) -> None:
        """Re-tripping updates reason."""
        db.trip_breaker("daily_loss", "first trigger")
        db.trip_breaker("daily_loss", "second trigger — worse")
        active = db.list_active_breakers()
        assert active[0].reason == "second trigger — worse"


# ======================================================================
# Concurrent writes
# ======================================================================


class TestConcurrency:
    def test_concurrent_writes_no_corruption(self, db: StateDB) -> None:
        """10 threads inserting orders simultaneously should all succeed."""

        def insert_order(i: int) -> None:
            db.insert_order(
                Order(
                    order_id=f"CONC-{i:03d}",
                    symbol="XAUUSD",
                    side="BUY",
                    volume=0.01,
                    client_tag=f"TAG-{i:03d}",
                )
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            futures = [ex.submit(insert_order, i) for i in range(10)]
            for f in futures:
                f.result()  # raise on exception

        stats = db.stats()
        assert stats["orders"] == 10


# ======================================================================
# Transaction
# ======================================================================


class TestTransaction:
    def test_transaction_rollback_on_error(self, db: StateDB) -> None:
        """Exception in transaction block rolls back changes."""
        db.insert_order(Order(order_id="TX-1", symbol="XAUUSD", side="BUY", volume=0.01))

        with pytest.raises(ValueError, match="boom"):
            with db.transaction() as conn:
                conn.execute(
                    "INSERT INTO orders (order_id, symbol, side, volume, order_type, status, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    ("TX-2", "XAUUSD", "BUY", 0.01, "MARKET", "PENDING", "2024-01-01", "2024-01-01"),
                )
                raise ValueError("boom")

        assert db.get_order("TX-2") is None  # rolled back
        assert db.get_order("TX-1") is not None  # unaffected


# ======================================================================
# Migration
# ======================================================================


class TestMigration:
    def test_migration_from_json(self, tmp_path: Path) -> None:
        """Migrate JSON state to SQLite and verify counts."""
        # Create a fake JSON state file
        json_path = tmp_path / "system_state.json"
        json_path.write_text("""
        {
            "system_state": "RUNNING",
            "positions": [
                {"symbol": "XAUUSD", "position_type": "LONG", "quantity": 0.01, "entry_price": 2350.0}
            ],
            "pending_orders": [
                {"id": "ORD-100", "symbol": "EURUSD", "side": "SELL", "qty": 0.1, "type": "MARKET", "price": 1.08}
            ],
            "circuit_breakers": {"daily_loss": true, "drawdown": false},
            "daily_pnl": -50.0,
            "peak_equity": 10000.0
        }
        """)

        from graxia.packages.quant_os.data.state_migration import migrate

        db_path = tmp_path / "test.db"
        db = StateDB(db_path)
        counts = migrate(json_path, db=db)

        assert counts["migrated"] is True
        assert counts["orders"] == 1
        assert counts["positions"] == 1
        assert counts["breakers"] == 2  # both entries iterated (true + false)

        # Verify data
        assert db.get_order("ORD-100") is not None
        pos = db.get_position("XAUUSD")
        assert pos is not None
        assert pos.side == "LONG"
        acc = db.get_account()
        assert acc.balance == 10000.0

        # Verify backup
        backups = list(tmp_path.glob("system_state.json.migrated.*"))
        assert len(backups) == 1

        db.close()

    def test_migration_missing_file(self, tmp_path: Path) -> None:
        """Missing JSON returns migrated=False."""
        from graxia.packages.quant_os.data.state_migration import migrate

        result = migrate(tmp_path / "nonexistent.json")
        assert result["migrated"] is False

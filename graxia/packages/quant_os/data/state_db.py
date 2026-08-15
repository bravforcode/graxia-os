"""SQLite-backed state persistence for the trading system.

Replaces the JSON-based ``core/state_store.py`` with ACID-compliant SQLite.
WAL mode enabled for concurrent reads. Thread-safe via threading.Lock.

Tables:
- orders: order lifecycle tracking
- positions: current open positions
- account_state: singleton account info
- circuit_breakers: kill switches / safety flags
- state_migrations: schema version tracking

Usage:
    from data.state_db import StateDB
    db = StateDB()
    db.insert_order(Order(...))
    orders = db.list_open_orders()
    db.close()
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
import logging

logger = logging.getLogger(__name__)


# ======================================================================
# Data classes (frozen=True for safety)
# ======================================================================


@dataclass(frozen=True)
class Order:
    """Immutable order record."""

    order_id: str
    symbol: str
    side: str  # BUY | SELL
    volume: float
    order_type: str = "MARKET"  # MARKET | LIMIT | STOP | STOP_LIMIT
    requested_price: float | None = None
    filled_price: float | None = None
    status: str = "PENDING"
    created_at: str = ""
    updated_at: str = ""
    venue: str = ""
    client_tag: str = ""
    metadata: str = "{}"

    def __post_init__(self) -> None:
        if not self.created_at:
            object.__setattr__(self, "created_at", _now_iso())
        if not self.updated_at:
            object.__setattr__(self, "updated_at", _now_iso())


@dataclass(frozen=True)
class Position:
    """Immutable position record."""

    symbol: str
    side: str  # LONG | SHORT | FLAT
    volume: float
    avg_entry_price: float
    unrealized_pnl: float = 0.0
    opened_at: str = ""
    updated_at: str = ""
    stop_loss: float | None = None
    take_profit: float | None = None
    metadata: str = "{}"

    def __post_init__(self) -> None:
        if not self.opened_at:
            object.__setattr__(self, "opened_at", _now_iso())
        if not self.updated_at:
            object.__setattr__(self, "updated_at", _now_iso())


@dataclass(frozen=True)
class AccountState:
    """Immutable account snapshot (singleton row)."""

    balance: float = 0.0
    equity: float = 0.0
    margin_used: float = 0.0
    margin_available: float = 0.0
    currency: str = "USD"
    leverage: float = 100.0
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not self.updated_at:
            object.__setattr__(self, "updated_at", _now_iso())


@dataclass(frozen=True)
class Breaker:
    """Immutable circuit breaker record."""

    name: str
    active: bool = False
    reason: str = ""
    triggered_at: str = ""
    reset_at: str = ""


# ======================================================================
# Helpers
# ======================================================================


def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ======================================================================
# Schema DDL
# ======================================================================

_SCHEMA_VERSION = 1

_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('BUY','SELL')),
    volume REAL NOT NULL CHECK(volume > 0),
    order_type TEXT NOT NULL DEFAULT 'MARKET',
    requested_price REAL,
    filled_price REAL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    venue TEXT DEFAULT '',
    client_tag TEXT DEFAULT '',
    metadata TEXT DEFAULT '{}'
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_client_tag
    ON orders(client_tag) WHERE client_tag != '';

CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);

CREATE TABLE IF NOT EXISTS positions (
    symbol TEXT PRIMARY KEY,
    side TEXT NOT NULL DEFAULT 'FLAT' CHECK(side IN ('LONG','SHORT','FLAT')),
    volume REAL NOT NULL DEFAULT 0,
    avg_entry_price REAL NOT NULL DEFAULT 0,
    unrealized_pnl REAL DEFAULT 0,
    opened_at TEXT,
    updated_at TEXT NOT NULL,
    stop_loss REAL,
    take_profit REAL,
    metadata TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS account_state (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    balance REAL NOT NULL,
    equity REAL NOT NULL,
    margin_used REAL DEFAULT 0,
    margin_available REAL DEFAULT 0,
    currency TEXT DEFAULT 'USD',
    leverage REAL DEFAULT 100,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS circuit_breakers (
    name TEXT PRIMARY KEY,
    active INTEGER NOT NULL DEFAULT 0,
    reason TEXT DEFAULT '',
    triggered_at TEXT,
    reset_at TEXT
);

CREATE TABLE IF NOT EXISTS state_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL,
    description TEXT DEFAULT ''
);
"""


# ======================================================================
# StateDB
# ======================================================================


class StateDB:
    """SQLite-backed state for orders, positions, account, circuit breakers.

    Thread-safe via ``check_same_thread=False`` + :class:`threading.Lock`
    for writes. WAL mode enabled for concurrent reads.
    """

    def __init__(self, db_path: str | Path = "data/state/quantos_state.db") -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
            isolation_level=None,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        """Create tables if not exist and record migration version."""
        with self._lock:
            self._conn.executescript(_SCHEMA_DDL)
            self._conn.execute(
                "INSERT OR IGNORE INTO state_migrations (version, applied_at, description) "
                "VALUES (?, ?, ?)",
                (_SCHEMA_VERSION, _now_iso(), "Initial schema"),
            )

    # ── Orders ────────────────────────────────────────────────────

    def insert_order(self, order: Order) -> None:
        """Insert an order. Raises sqlite3.IntegrityError on duplicate client_tag."""
        # Use NULL for empty client_tag so partial UNIQUE index doesn't conflict
        client_tag = order.client_tag if order.client_tag else None
        with self._lock:
            self._conn.execute(
                """INSERT INTO orders
                   (order_id, symbol, side, volume, order_type, requested_price,
                    filled_price, status, created_at, updated_at, venue, client_tag, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    order.order_id, order.symbol, order.side, order.volume,
                    order.order_type, order.requested_price, order.filled_price,
                    order.status, order.created_at, order.updated_at,
                    order.venue, client_tag, order.metadata,
                ),
            )

    def update_order_status(
        self, order_id: str, status: str, filled_price: float | None = None
    ) -> None:
        """Update order status and optionally the filled price."""
        with self._lock:
            self._conn.execute(
                """UPDATE orders
                   SET status = ?, filled_price = COALESCE(?, filled_price), updated_at = ?
                   WHERE order_id = ?""",
                (status, filled_price, _now_iso(), order_id),
            )

    def get_order(self, order_id: str) -> Order | None:
        """Return order by ID, or None if not found."""
        row = self._conn.execute(
            "SELECT * FROM orders WHERE order_id = ?", (order_id,)
        ).fetchone()
        return _row_to_order(row) if row else None

    def list_open_orders(self) -> list[Order]:
        """Return all orders not in a terminal state."""
        terminal = ("FILLED", "CANCELLED", "REJECTED", "EXPIRED", "FAILED", "ERROR")
        rows = self._conn.execute(
            "SELECT * FROM orders WHERE status NOT IN (?,?,?,?,?,?) ORDER BY created_at",
            terminal,
        ).fetchall()
        return [_row_to_order(r) for r in rows]

    def list_orders_by_date_range(self, start: str, end: str) -> list[Order]:
        """Return orders created within [start, end] ISO date range."""
        rows = self._conn.execute(
            "SELECT * FROM orders WHERE created_at BETWEEN ? AND ? ORDER BY created_at",
            (start, end),
        ).fetchall()
        return [_row_to_order(r) for r in rows]

    # ── Positions ─────────────────────────────────────────────────

    def upsert_position(self, position: Position) -> None:
        """Insert or update a position (upsert on symbol)."""
        with self._lock:
            self._conn.execute(
                """INSERT INTO positions
                   (symbol, side, volume, avg_entry_price, unrealized_pnl,
                    opened_at, updated_at, stop_loss, take_profit, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(symbol) DO UPDATE SET
                       side = excluded.side,
                       volume = excluded.volume,
                       avg_entry_price = excluded.avg_entry_price,
                       unrealized_pnl = excluded.unrealized_pnl,
                       updated_at = excluded.updated_at,
                       stop_loss = excluded.stop_loss,
                       take_profit = excluded.take_profit,
                       metadata = excluded.metadata""",
                (
                    position.symbol, position.side, position.volume,
                    position.avg_entry_price, position.unrealized_pnl,
                    position.opened_at, _now_iso(),
                    position.stop_loss, position.take_profit, position.metadata,
                ),
            )

    def close_position(self, symbol: str, close_price: float) -> None:
        """Close a position: set volume=0, side=FLAT, update timestamp."""
        with self._lock:
            self._conn.execute(
                """UPDATE positions
                   SET side = 'FLAT', volume = 0, updated_at = ?
                   WHERE symbol = ?""",
                (_now_iso(), symbol),
            )

    def get_position(self, symbol: str) -> Position | None:
        """Return position by symbol, or None if not found."""
        row = self._conn.execute(
            "SELECT * FROM positions WHERE symbol = ?", (symbol,)
        ).fetchone()
        return _row_to_position(row) if row else None

    def list_positions(self) -> list[Position]:
        """Return all positions."""
        rows = self._conn.execute("SELECT * FROM positions ORDER BY symbol").fetchall()
        return [_row_to_position(r) for r in rows]

    # ── Account ───────────────────────────────────────────────────

    def update_account(self, account: AccountState) -> None:
        """Insert or update the singleton account row (id=1)."""
        with self._lock:
            self._conn.execute(
                """INSERT INTO account_state (id, balance, equity, margin_used, margin_available, currency, leverage, updated_at)
                   VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                       balance = excluded.balance,
                       equity = excluded.equity,
                       margin_used = excluded.margin_used,
                       margin_available = excluded.margin_available,
                       currency = excluded.currency,
                       leverage = excluded.leverage,
                       updated_at = excluded.updated_at""",
                (
                    account.balance, account.equity, account.margin_used,
                    account.margin_available, account.currency, account.leverage,
                    _now_iso(),
                ),
            )

    def get_account(self) -> AccountState:
        """Return account state. Returns zero-equity state (fail-closed) if no row exists."""
        row = self._conn.execute("SELECT * FROM account_state WHERE id = 1").fetchone()
        return _row_to_account(row) if row else AccountState(equity=0.0, balance=0.0)

    # ── Circuit Breakers ──────────────────────────────────────────

    def trip_breaker(self, name: str, reason: str) -> None:
        """Activate a circuit breaker."""
        with self._lock:
            self._conn.execute(
                """INSERT INTO circuit_breakers (name, active, reason, triggered_at)
                   VALUES (?, 1, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET
                       active = 1, reason = excluded.reason, triggered_at = excluded.triggered_at, reset_at = NULL""",
                (name, reason, _now_iso()),
            )

    def reset_breaker(self, name: str) -> None:
        """Deactivate a circuit breaker."""
        with self._lock:
            self._conn.execute(
                "UPDATE circuit_breakers SET active = 0, reset_at = ? WHERE name = ?",
                (_now_iso(), name),
            )

    def list_active_breakers(self) -> list[Breaker]:
        """Return all active circuit breakers."""
        rows = self._conn.execute(
            "SELECT * FROM circuit_breakers WHERE active = 1"
        ).fetchall()
        return [_row_to_breaker(r) for r in rows]

    # ── Generic ───────────────────────────────────────────────────

    def vacuum(self) -> None:
        """Compact the database file."""
        with self._lock:
            self._conn.execute("VACUUM")

    def stats(self) -> dict[str, int]:
        """Return row counts for all tables."""
        tables = ("orders", "positions", "account_state", "circuit_breakers")
        result = {}
        for tbl in tables:
            result[tbl] = self._conn.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
        result["schema_version"] = _SCHEMA_VERSION
        return result

    def close(self) -> None:
        """Close the database connection (idempotent)."""
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                # ponytail: was bare pass, now logged
                logger.debug("exception_suppressed", exc_info=True)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Context manager for explicit transaction with auto-rollback."""
        with self._lock:
            try:
                self._conn.execute("BEGIN")
                yield self._conn
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise

    def __enter__(self) -> StateDB:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


# ======================================================================
# Row → dataclass converters
# ======================================================================


def _row_to_order(row: sqlite3.Row) -> Order:
    return Order(
        order_id=row["order_id"],
        symbol=row["symbol"],
        side=row["side"],
        volume=row["volume"],
        order_type=row["order_type"],
        requested_price=row["requested_price"],
        filled_price=row["filled_price"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        venue=row["venue"] or "",
        client_tag=row["client_tag"] or "",
        metadata=row["metadata"] or "{}",
    )


def _row_to_position(row: sqlite3.Row) -> Position:
    return Position(
        symbol=row["symbol"],
        side=row["side"],
        volume=row["volume"],
        avg_entry_price=row["avg_entry_price"],
        unrealized_pnl=row["unrealized_pnl"],
        opened_at=row["opened_at"] or "",
        updated_at=row["updated_at"],
        stop_loss=row["stop_loss"],
        take_profit=row["take_profit"],
        metadata=row["metadata"] or "{}",
    )


def _row_to_account(row: sqlite3.Row) -> AccountState:
    return AccountState(
        balance=row["balance"],
        equity=row["equity"],
        margin_used=row["margin_used"],
        margin_available=row["margin_available"],
        currency=row["currency"],
        leverage=row["leverage"],
        updated_at=row["updated_at"],
    )


def _row_to_breaker(row: sqlite3.Row) -> Breaker:
    return Breaker(
        name=row["name"],
        active=bool(row["active"]),
        reason=row["reason"] or "",
        triggered_at=row["triggered_at"] or "",
        reset_at=row["reset_at"] or "",
    )

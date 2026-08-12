"""Position ledger with SQLite backend — WAL mode, daily P&L, drawdown tracking."""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, UTC
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable, Optional



def _dec(v: Any) -> Decimal:
    """Coerce to Decimal safely."""
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def _dec_str(v: Decimal) -> str:
    """Decimal → string for storage."""
    return str(v.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP))


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _midnight_utc() -> datetime:
    now = _now_utc()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


@dataclass
class Position:
    """Single open position record."""
    position_id: str
    symbol: str
    asset_class: str
    venue: str
    side: str  # "LONG" | "SHORT"
    quantity: Decimal
    entry_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    swap_cost: Decimal
    commission: Decimal
    opened_at: datetime
    updated_at: datetime
    signal_id: str = ""
    strategy_id: str = ""
    broker_position_id: str = ""
    metadata_json: str = ""


@dataclass
class VenueBreakdown:
    """Per-venue exposure summary."""
    venue: str
    position_count: int
    total_exposure: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal


@dataclass
class Portfolio:
    """Aggregated portfolio snapshot."""
    total_equity: Decimal
    total_unrealized: Decimal
    total_realized: Decimal
    daily_pnl: Decimal
    weekly_pnl: Decimal
    peak_equity: Decimal
    current_drawdown_pct: Decimal
    positions: list[Position]
    venue_breakdown: list[VenueBreakdown]
    asset_class_exposure_pct: dict[str, Decimal]
    last_reconciled: Optional[datetime]
    reconcile_ok: bool


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS positions (
    position_id     TEXT PRIMARY KEY,
    symbol          TEXT NOT NULL,
    asset_class     TEXT NOT NULL DEFAULT '',
    venue           TEXT NOT NULL DEFAULT '',
    side            TEXT NOT NULL,
    quantity        TEXT NOT NULL,
    entry_price     TEXT NOT NULL,
    current_price   TEXT NOT NULL,
    unrealized_pnl  TEXT NOT NULL DEFAULT '0',
    realized_pnl    TEXT NOT NULL DEFAULT '0',
    swap_cost       TEXT NOT NULL DEFAULT '0',
    commission      TEXT NOT NULL DEFAULT '0',
    opened_at       TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    signal_id       TEXT NOT NULL DEFAULT '',
    strategy_id     TEXT NOT NULL DEFAULT '',
    broker_position_id TEXT NOT NULL DEFAULT '',
    metadata_json   TEXT NOT NULL DEFAULT '{}',
    is_open         INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS fills (
    fill_id         TEXT PRIMARY KEY,
    position_id     TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL,
    quantity        TEXT NOT NULL,
    price           TEXT NOT NULL,
    commission      TEXT NOT NULL DEFAULT '0',
    swap_cost       TEXT NOT NULL DEFAULT '0',
    filled_at       TEXT NOT NULL,
    broker_fill_id  TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (position_id) REFERENCES positions(position_id)
);

CREATE TABLE IF NOT EXISTS daily_pnl (
    date            TEXT PRIMARY KEY,
    realized_pnl    TEXT NOT NULL DEFAULT '0',
    unrealized_pnl  TEXT NOT NULL DEFAULT '0',
    total_pnl       TEXT NOT NULL DEFAULT '0',
    peak_equity     TEXT NOT NULL DEFAULT '0',
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS equity_snapshots (
    snapshot_id     TEXT PRIMARY KEY,
    equity          TEXT NOT NULL,
    recorded_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);
CREATE INDEX IF NOT EXISTS idx_positions_venue ON positions(venue);
CREATE INDEX IF NOT EXISTS idx_positions_is_open ON positions(is_open);
CREATE INDEX IF NOT EXISTS idx_fills_position ON fills(position_id);
"""


class Ledger:
    """SQLite-backed position ledger with WAL mode, daily P&L, drawdown tracking.

    Usage:
        ledger = Ledger("data/ledger.db")
        pos = ledger.save_position(Position(...))
        ledger.apply_fill(pos.position_id, Decimal("0.1"), Decimal("2025.50"), ...)
        pf = ledger.calculate_portfolio(initial_equity=Decimal("10000"))
    """

    def __init__(
        self,
        db_path: str = "ledger.db",
        initial_equity: Decimal = Decimal("0"),
    ) -> None:
        self._db_path = db_path
        self._initial_equity = _dec(initial_equity)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        self._ensure_daily_pnl_row()

    def close(self) -> None:
        self._conn.close()

    # -- schema -----------------------------------------------------------

    def _init_schema(self) -> None:
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.commit()

    # -- position CRUD ----------------------------------------------------

    def save_position(self, pos: Position) -> Position:
        """Insert a new open position."""
        if not pos.position_id:
            pos.position_id = f"pos-{uuid.uuid4().hex[:12]}"
        now = _now_utc()
        if not pos.opened_at:
            pos.opened_at = now
        if not pos.updated_at:
            pos.updated_at = now
        self._conn.execute(
            """INSERT INTO positions
               (position_id, symbol, asset_class, venue, side, quantity,
                entry_price, current_price, unrealized_pnl, realized_pnl,
                swap_cost, commission, opened_at, updated_at, signal_id,
                strategy_id, broker_position_id, metadata_json, is_open)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
            _pos_row(pos),
        )
        self._conn.commit()
        return pos

    def update_position(self, pos: Position) -> None:
        """Update an existing position (price, P&L, etc.)."""
        pos.updated_at = _now_utc()
        self._conn.execute(
            """UPDATE positions SET
                symbol=?, asset_class=?, venue=?, side=?, quantity=?,
                entry_price=?, current_price=?, unrealized_pnl=?, realized_pnl=?,
                swap_cost=?, commission=?, opened_at=?, updated_at=?,
                signal_id=?, strategy_id=?, broker_position_id=?, metadata_json=?
               WHERE position_id=?""",
            (*_pos_row(pos)[1:], pos.position_id),
        )
        self._conn.commit()

    def close_position(self, position_id: str, realized_pnl: Decimal = Decimal("0")) -> None:
        """Mark position as closed."""
        now = _now_utc()
        self._conn.execute(
            """UPDATE positions SET is_open=0, realized_pnl=?, updated_at=?
               WHERE position_id=?""",
            (_dec_str(realized_pnl), now.isoformat(), position_id),
        )
        self._conn.commit()

    def get_by_id(self, position_id: str) -> Optional[Position]:
        row = self._conn.execute(
            "SELECT * FROM positions WHERE position_id=?", (position_id,)
        ).fetchone()
        return _row_to_pos(row) if row else None

    def get_all_open(self) -> list[Position]:
        rows = self._conn.execute(
            "SELECT * FROM positions WHERE is_open=1 ORDER BY opened_at"
        ).fetchall()
        return [_row_to_pos(r) for r in rows]

    def get_by_venue(self, venue: str) -> list[Position]:
        rows = self._conn.execute(
            "SELECT * FROM positions WHERE venue=? AND is_open=1", (venue,)
        ).fetchall()
        return [_row_to_pos(r) for r in rows]

    def get_by_symbol(self, symbol: str) -> list[Position]:
        rows = self._conn.execute(
            "SELECT * FROM positions WHERE symbol=? AND is_open=1", (symbol,)
        ).fetchall()
        return [_row_to_pos(r) for r in rows]

    def get_by_signal_id(self, signal_id: str) -> Optional[Position]:
        row = self._conn.execute(
            "SELECT * FROM positions WHERE signal_id=? AND is_open=1", (signal_id,)
        ).fetchone()
        return _row_to_pos(row) if row else None

    # -- fills -----------------------------------------------------------

    def apply_fill(
        self,
        position_id: str,
        fill_qty: Decimal,
        fill_price: Decimal,
        commission: Decimal = Decimal("0"),
        swap_cost: Decimal = Decimal("0"),
        broker_fill_id: str = "",
    ) -> Position:
        """Record a fill, update position quantity and avg price.

        For new positions, creates one. For existing, adjusts avg price.
        Returns the updated position.
        """
        fill_id = f"fill-{uuid.uuid4().hex[:12]}"
        now = _now_utc()
        existing = self.get_by_id(position_id)

        if existing is None:
            raise ValueError(f"Position {position_id} not found")

        # Weighted average price
        old_qty = existing.quantity
        new_qty = old_qty + fill_qty
        if new_qty > 0:
            avg = (existing.entry_price * old_qty + fill_price * fill_qty) / new_qty
            existing.entry_price = avg
        existing.quantity = new_qty
        existing.commission += _dec(commission)
        existing.swap_cost += _dec(swap_cost)
        existing.current_price = fill_price
        existing.updated_at = now

        self._conn.execute(
            """INSERT INTO fills
               (fill_id, position_id, symbol, side, quantity, price,
                commission, swap_cost, filled_at, broker_fill_id)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                fill_id, position_id, existing.symbol, existing.side,
                _dec_str(fill_qty), _dec_str(fill_price),
                _dec_str(_dec(commission)), _dec_str(_dec(swap_cost)),
                now.isoformat(), broker_fill_id,
            ),
        )
        self.update_position(existing)
        return existing

    # -- daily P&L -------------------------------------------------------

    def _ensure_daily_pnl_row(self) -> None:
        today = _midnight_utc().strftime("%Y-%m-%d")
        now = _now_utc().isoformat()
        self._conn.execute(
            """INSERT OR IGNORE INTO daily_pnl (date, realized_pnl, unrealized_pnl, total_pnl, peak_equity, updated_at)
               VALUES (?, '0', '0', '0', '0', ?)""",
            (today, now),
        )
        self._conn.commit()

    def record_daily_pnl(
        self,
        realized: Decimal,
        unrealized: Decimal,
        peak_equity: Decimal,
    ) -> None:
        """Update today's P&L row."""
        today = _midnight_utc().strftime("%Y-%m-%d")
        total = realized + unrealized
        now = _now_utc().isoformat()
        self._conn.execute(
            """INSERT INTO daily_pnl (date, realized_pnl, unrealized_pnl, total_pnl, peak_equity, updated_at)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(date) DO UPDATE SET
                 realized_pnl=excluded.realized_pnl,
                 unrealized_pnl=excluded.unrealized_pnl,
                 total_pnl=excluded.total_pnl,
                 peak_equity=excluded.peak_equity,
                 updated_at=excluded.updated_at""",
            (today, _dec_str(realized), _dec_str(unrealized),
             _dec_str(total), _dec_str(peak_equity), now),
        )
        self._conn.commit()

    def get_daily_pnl(self, date_str: str | None = None) -> Decimal:
        """Get total P&L for a specific date (default: today)."""
        if date_str is None:
            date_str = _midnight_utc().strftime("%Y-%m-%d")
        row = self._conn.execute(
            "SELECT total_pnl FROM daily_pnl WHERE date=?", (date_str,)
        ).fetchone()
        return _dec(row["total_pnl"]) if row else Decimal("0")

    def get_weekly_pnl(self) -> Decimal:
        """Sum of daily P&L for the last 7 days."""
        start = (_midnight_utc() - timedelta(days=7)).strftime("%Y-%m-%d")
        rows = self._conn.execute(
            "SELECT total_pnl FROM daily_pnl WHERE date >= ?", (start,)
        ).fetchall()
        return sum((_dec(r["total_pnl"]) for r in rows), Decimal("0"))

    # -- equity snapshots ------------------------------------------------

    def record_equity_snapshot(self, equity: Decimal) -> None:
        sid = f"eq-{uuid.uuid4().hex[:8]}"
        now = _now_utc().isoformat()
        self._conn.execute(
            "INSERT INTO equity_snapshots (snapshot_id, equity, recorded_at) VALUES (?,?,?)",
            (sid, _dec_str(equity), now),
        )
        self._conn.commit()

    def get_peak_equity(self) -> Decimal:
        """Highest equity ever recorded (from snapshots + daily_pnl)."""
        row = self._conn.execute(
            "SELECT MAX(CAST(equity AS REAL)) as peak FROM equity_snapshots"
        ).fetchone()
        if row and row["peak"] is not None:
            return _dec(str(row["peak"]))
        return self._initial_equity

    # -- portfolio calculation -------------------------------------------

    def calculate_portfolio(
        self,
        price_fn: Callable[[str], Decimal] | None = None,
        initial_equity: Decimal | None = None,
    ) -> Portfolio:
        """Build a Portfolio snapshot.

        Args:
            price_fn: Optional callable(symbol) -> current_price.
                      If None, uses stored current_price on each position.
            initial_equity: Override for initial equity (fallback: constructor value).
        """
        eq = _dec(initial_equity) if initial_equity else self._initial_equity
        positions = self.get_all_open()

        # Update prices if price_fn provided
        if price_fn:
            for p in positions:
                p.current_price = _dec(price_fn(p.symbol))
                diff = p.current_price - p.entry_price
                if p.side == "SHORT":
                    diff = -diff
                p.unrealized_pnl = diff * p.quantity - p.commission - p.swap_cost
                self.update_position(p)

        total_unrealized = sum((p.unrealized_pnl for p in positions), Decimal("0"))
        total_realized = sum((p.realized_pnl for p in positions), Decimal("0"))
        total_equity = eq + total_realized + total_unrealized

        # Peak equity & drawdown
        peak = max(self.get_peak_equity(), total_equity)
        if peak > 0:
            dd_pct = ((peak - total_equity) / peak * Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            dd_pct = Decimal("0")

        # Record snapshot
        self.record_equity_snapshot(total_equity)

        # Daily / weekly P&L
        self.record_daily_pnl(total_realized, total_unrealized, peak)
        daily_pnl = self.get_daily_pnl()
        weekly_pnl = self.get_weekly_pnl()

        # Venue breakdown
        venue_map: dict[str, list[Position]] = {}
        for p in positions:
            venue_map.setdefault(p.venue, []).append(p)
        venue_breakdown = []
        for venue, vpos in venue_map.items():
            total_exp = sum((p.entry_price * p.quantity for p in vpos), Decimal("0"))
            venue_breakdown.append(VenueBreakdown(
                venue=venue,
                position_count=len(vpos),
                total_exposure=total_exp,
                unrealized_pnl=sum((p.unrealized_pnl for p in vpos), Decimal("0")),
                realized_pnl=sum((p.realized_pnl for p in vpos), Decimal("0")),
            ))

        # Asset class exposure %
        class_map: dict[str, Decimal] = {}
        for p in positions:
            exp = p.entry_price * p.quantity
            class_map[p.asset_class] = class_map.get(p.asset_class, Decimal("0")) + exp
        total_exposure = sum(class_map.values(), Decimal("0"))
        class_pct: dict[str, Decimal] = {}
        for cls, exp in class_map.items():
            if total_exposure > 0:
                class_pct[cls] = (exp / total_exposure * Decimal("100")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            else:
                class_pct[cls] = Decimal("0")

        # Last reconcile
        lr_row = self._conn.execute(
            "SELECT MAX(recorded_at) FROM equity_snapshots"
        ).fetchone()
        last_reconciled = None
        if lr_row and lr_row[0]:
            last_reconciled = datetime.fromisoformat(lr_row[0])

        return Portfolio(
            total_equity=total_equity,
            total_unrealized=total_unrealized,
            total_realized=total_realized,
            daily_pnl=daily_pnl,
            weekly_pnl=weekly_pnl,
            peak_equity=peak,
            current_drawdown_pct=dd_pct,
            positions=positions,
            venue_breakdown=venue_breakdown,
            asset_class_exposure_pct=class_pct,
            last_reconciled=last_reconciled,
            reconcile_ok=True,
        )


# -- helpers --------------------------------------------------------------

def _pos_row(p: Position) -> tuple:
    return (
        p.position_id, p.symbol, p.asset_class, p.venue, p.side,
        _dec_str(p.quantity), _dec_str(p.entry_price), _dec_str(p.current_price),
        _dec_str(p.unrealized_pnl), _dec_str(p.realized_pnl),
        _dec_str(p.swap_cost), _dec_str(p.commission),
        p.opened_at.isoformat(), p.updated_at.isoformat(),
        p.signal_id, p.strategy_id, p.broker_position_id, p.metadata_json,
    )


def _row_to_pos(row: sqlite3.Row) -> Position:
    return Position(
        position_id=row["position_id"],
        symbol=row["symbol"],
        asset_class=row["asset_class"],
        venue=row["venue"],
        side=row["side"],
        quantity=_dec(row["quantity"]),
        entry_price=_dec(row["entry_price"]),
        current_price=_dec(row["current_price"]),
        unrealized_pnl=_dec(row["unrealized_pnl"]),
        realized_pnl=_dec(row["realized_pnl"]),
        swap_cost=_dec(row["swap_cost"]),
        commission=_dec(row["commission"]),
        opened_at=datetime.fromisoformat(row["opened_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        signal_id=row["signal_id"],
        strategy_id=row["strategy_id"],
        broker_position_id=row["broker_position_id"],
        metadata_json=row["metadata_json"],
    )

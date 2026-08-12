"""
Shadow Trades — simulated trade execution engine for paper-trading.

Listens to signals from the EventBus, opens/closes simulated trades in DuckDB,
and tracks PnL with slippage and cost modeling. Trades that exceed the max
holding period are auto-closed with reason TIMEOUT.

Usage:
    trader = ShadowTrader(write_queue, db_path="data/shadow_trades.duckdb")
    await trader.start()
    # Wire up to EventBus:
    bus.subscribe("signal.new", trader.on_signal)
    ...
    await trader.stop()
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

import duckdb
import structlog

from core.canonical.payloads import SignalNewPayload
from data.duckdb_write_queue import DuckDBWriteQueue

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MAX_HOLDING_HOURS: float = 4.0
DEFAULT_SLIPPAGE_POINTS: float = 0.3
DEFAULT_COST_POINTS: float = 0.5

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TradeSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class TradeStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class CloseReason(str, Enum):
    SL = "SL"
    TP = "TP"
    TIMEOUT = "TIMEOUT"
    MANUAL = "MANUAL"


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------


@dataclass
class ShadowTrade:
    """In-memory representation of a simulated trade."""

    trade_id: str
    symbol: str
    side: TradeSide
    entry_price: float
    quantity: float
    strategy: str
    signal_id: str
    slippage_points: float
    cost_points: float
    opened_at: datetime
    status: TradeStatus = TradeStatus.OPEN
    exit_price: float | None = None
    pnl: float | None = None
    pnl_pct: float | None = None
    closed_at: datetime | None = None
    close_reason: CloseReason | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict suitable for DuckDB insert."""
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "quantity": self.quantity,
            "pnl": self.pnl,
            "pnl_pct": self.pnl_pct,
            "status": self.status.value,
            "strategy": self.strategy,
            "signal_id": self.signal_id,
            "slippage_points": self.slippage_points,
            "cost_points": self.cost_points,
            "opened_at": self.opened_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "close_reason": self.close_reason.value if self.close_reason else None,
        }


# ---------------------------------------------------------------------------
# Table schema (used by DuckDBWriteQueue and direct connection)
# ---------------------------------------------------------------------------

SHADOW_TRADES_DDL = """
CREATE TABLE IF NOT EXISTS shadow_trades (
    trade_id        TEXT PRIMARY KEY,
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL,
    entry_price     DOUBLE NOT NULL,
    exit_price      DOUBLE,
    quantity        DOUBLE NOT NULL,
    pnl             DOUBLE,
    pnl_pct         DOUBLE,
    status          TEXT NOT NULL DEFAULT 'OPEN',
    strategy        TEXT NOT NULL,
    signal_id       TEXT NOT NULL,
    slippage_points DOUBLE NOT NULL DEFAULT 0.0,
    cost_points     DOUBLE NOT NULL DEFAULT 0.0,
    opened_at       TIMESTAMP NOT NULL,
    closed_at       TIMESTAMP,
    close_reason    TEXT
);
"""

# ---------------------------------------------------------------------------
# ShadowTrader
# ---------------------------------------------------------------------------


class ShadowTrader:
    """
    Simulated trade executor backed by DuckDB.

    - Subscribes to ``signal.new`` on the EventBus.
    - Opens trades via :meth:`open_trade` on signal reception.
    - Closes trades via :meth:`close_trade` when SL/TP/tick price is hit.
    - Auto-closes stale trades that exceed ``max_holding_hours``.

    Args:
        write_queue: An initialised :class:`DuckDBWriteQueue` for async writes.
        db_path: Direct DuckDB path for reads and DDL bootstrap.
        max_holding_hours: Auto-close threshold (default 4 h).
        slippage_points: Assumed slippage per trade (default 0.3 pts).
        cost_points: Assumed spread/commission cost (default 0.5 pts).
    """

    def __init__(
        self,
        write_queue: DuckDBWriteQueue,
        db_path: str = "data/shadow_trades.duckdb",
        max_holding_hours: float = DEFAULT_MAX_HOLDING_HOURS,
        slippage_points: float = DEFAULT_SLIPPAGE_POINTS,
        cost_points: float = DEFAULT_COST_POINTS,
    ) -> None:
        self._write_queue = write_queue
        self._db_path = db_path
        self._max_holding = timedelta(hours=max_holding_hours)
        self._slippage = slippage_points
        self._cost = cost_points
        self._open_trades: dict[str, ShadowTrade] = {}
        self._cleanup_task: asyncio.Task[None] | None = None
        self._running = False
        self._ensure_table()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the background cleanup loop."""
        if self._running:
            return
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop(), name="shadow_trade_cleanup")
        logger.info("shadow_trader.started")

    async def stop(self) -> None:
        """Stop the cleanup loop."""
        self._running = False
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
        logger.info("shadow_trader.stopped")

    # ------------------------------------------------------------------
    # EventBus integration
    # ------------------------------------------------------------------

    async def on_signal(self, data: Any) -> None:
        """
        EventBus callback for ``signal.new`` events.

        Accepts a ``SignalNewPayload`` (Pydantic v2) or falls back to dict
        for backward compatibility.
        """
        if isinstance(data, SignalNewPayload):
            current_price = data.entry_price
            if current_price <= 0:
                logger.warning("shadow_trader.invalid_price", data=data)
                return

            trade = self.open_trade(
                signal=data,
                current_price=current_price,
            )
        elif isinstance(data, dict):
            current_price = data.get("entry_price", 0.0)
            if current_price <= 0:
                logger.warning("shadow_trader.invalid_price", data=data)
                return

            trade = self.open_trade(
                signal=data,
                current_price=current_price,
            )
        else:
            logger.warning("shadow_trader.invalid_signal_data", data=data)
            return

        logger.info(
            "shadow_trader.trade_opened",
            trade_id=trade.trade_id,
            symbol=trade.symbol,
            side=trade.side.value,
        )

    # ------------------------------------------------------------------
    # Trade management
    # ------------------------------------------------------------------

    def open_trade(
        self,
        signal: SignalNewPayload | dict[str, Any],
        current_price: float,
        quantity: float = 0.01,
    ) -> ShadowTrade:
        """
        Create an OPEN trade from a signal and persist it.

        Args:
            signal: SignalNewPayload (Pydantic) or dict with ``symbol``,
                    ``side``, ``entry_price``, ``strategy``, ``signal_id``.
            current_price: Current market price at open.
            quantity: Trade size (default 0.01 lots).

        Returns:
            The newly created :class:`ShadowTrade`.
        """
        if isinstance(signal, SignalNewPayload):
            side_str = signal.side.value.upper() if hasattr(signal.side, "value") else str(signal.side).upper()
            entry_price = signal.entry_price
            symbol = signal.symbol
            strategy = signal.strategy
            signal_id = signal.signal_id or uuid.uuid4().hex[:16]
        else:
            side_str = signal.get("side", "BUY").upper()
            entry_price = signal.get("entry_price", current_price)
            symbol = signal.get("symbol", "XAUUSD")
            strategy = signal.get("strategy", "unknown")
            signal_id = signal.get("signal_id", uuid.uuid4().hex[:16])

        trade = ShadowTrade(
            trade_id=uuid.uuid4().hex[:12],
            symbol=symbol,
            side=TradeSide(side_str),
            entry_price=entry_price,
            quantity=quantity,
            strategy=strategy,
            signal_id=signal_id,
            slippage_points=self._slippage,
            cost_points=self._cost,
            opened_at=datetime.now(UTC),
        )
        self._open_trades[trade.trade_id] = trade
        self._write_trade(trade)
        return trade

    def close_trade(
        self,
        trade_id: str,
        exit_price: float,
        reason: str = "MANUAL",
    ) -> ShadowTrade | None:
        """
        Close an open trade, calculate PnL, and persist the update.

        PnL = raw_pnl - slippage - cost
          where raw_pnl = (exit - entry) for BUY, (entry - exit) for SELL.

        Args:
            trade_id: ID of the trade to close.
            exit_price: Market price at close.
            reason: One of SL/TP/TIMEOUT/MANUAL.

        Returns:
            Updated :class:`ShadowTrade` or None if not found.
        """
        trade = self._open_trades.get(trade_id)
        if trade is None or trade.status != TradeStatus.OPEN:
            logger.warning("shadow_trader.close_not_found", trade_id=trade_id)
            return None

        trade.exit_price = exit_price
        trade.closed_at = datetime.now(UTC)
        trade.close_reason = CloseReason(reason.upper())

        # Raw PnL before costs
        if trade.side == TradeSide.BUY:
            raw_pnl = (exit_price - trade.entry_price) * trade.quantity
        else:
            raw_pnl = (trade.entry_price - exit_price) * trade.quantity

        # Net PnL = raw - slippage - cost
        trade.pnl = raw_pnl - trade.slippage_points - trade.cost_points
        trade.pnl_pct = (
            (trade.pnl / (trade.entry_price * trade.quantity)) * 100.0
            if trade.entry_price * trade.quantity > 0
            else 0.0
        )
        trade.status = TradeStatus.CLOSED
        self._open_trades.pop(trade_id, None)
        self._write_trade(trade)

        logger.info(
            "shadow_trader.trade_closed",
            trade_id=trade_id,
            pnl=trade.pnl,
            reason=reason,
        )
        return trade

    # ------------------------------------------------------------------
    # Periodic cleanup
    # ------------------------------------------------------------------

    async def _cleanup_loop(self) -> None:
        """Auto-close trades exceeding max holding period every 60s."""
        while self._running:
            try:
                await asyncio.sleep(60.0)
                self._auto_close_stale()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("shadow_trader.cleanup_error")

    def _auto_close_stale(self) -> None:
        """Close open trades that have exceeded the max holding period."""
        now = datetime.now(UTC)
        stale_ids = [tid for tid, t in self._open_trades.items() if now - t.opened_at > self._max_holding]
        for tid in stale_ids:
            trade = self._open_trades.get(tid)
            if trade is None:
                continue
            # Use current entry_price as proxy if no live exit available
            self.close_trade(tid, trade.entry_price, reason="TIMEOUT")

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _write_trade(self, trade: ShadowTrade) -> None:
        """Enqueue a trade write to the DuckDBWriteQueue."""
        try:
            asyncio.get_event_loop().run_coroutine_threadsafe(
                self._write_queue.enqueue("shadow_trades", [trade.to_dict()]),
                asyncio.get_event_loop(),
            )
        except Exception:
            # Fallback: write directly if no running loop
            self._write_trade_sync(trade)

    def _write_trade_sync(self, trade: ShadowTrade) -> None:
        """Direct synchronous DuckDB write (fallback)."""
        try:
            conn = duckdb.connect(self._db_path)
            conn.execute(SHADOW_TRADES_DDL)
            d = trade.to_dict()
            cols = list(d.keys())
            placeholders = ", ".join(["?"] * len(cols))
            col_names = ", ".join(cols)
            sql = f"INSERT OR REPLACE INTO shadow_trades ({col_names}) " f"VALUES ({placeholders})"
            conn.execute(sql, list(d.values()))
            conn.close()
        except Exception:
            logger.exception("shadow_trader.sync_write_error", trade_id=trade.trade_id)

    def _ensure_table(self) -> None:
        """Create the shadow_trades table if it doesn't exist."""
        try:
            conn = duckdb.connect(self._db_path)
            conn.execute(SHADOW_TRADES_DDL)
            conn.close()
        except Exception:
            logger.exception("shadow_trader.ensure_table_error")

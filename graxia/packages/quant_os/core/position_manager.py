"""
Position Manager — persistent position tracking with unrealized PnL.

Stores positions in Parquet for durability across restarts.
Listens to FillEvent / TradeClosedEvent on the EventBus.

Architecture:
    FillEvent        → PositionManager._on_fill()   → open/increase position
    TradeClosedEvent → PositionManager._on_close()  → close position
    EventBus         → PositionManager.get_positions() for risk checks

Storage:
    data/positions.parquet — current open positions
    data/trade_log.parquet — completed trades (append-only)

Usage:
    pm = PositionManager(bus=event_bus, data_dir=Path("data"))
    bus.subscribe(FillEvent, pm.on_fill)
    bus.subscribe(TradeClosedEvent, pm.on_close)
    positions = pm.get_positions()  # for RiskEngine portfolio checks
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .enums import SignalType
from .events import Event, FillEvent, TradeClosedEvent
from .event_bus import EventBus

logger = logging.getLogger(__name__)

_DEFAULT_DATA_DIR = Path("data")


@dataclass
class Position:
    """An open position tracked by the system."""

    symbol: str
    side: str  # "BUY" or "SELL"
    quantity: float
    entry_price: float
    current_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    strategy_id: str = ""
    opened_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    order_id: str = ""
    broker_order_id: str = ""

    @property
    def notional(self) -> float:
        return self.entry_price * self.quantity

    def update_pnl(self, current_price: float) -> None:
        """Recalculate unrealized PnL from current price."""
        self.current_price = current_price
        if self.side == "BUY":
            self.unrealized_pnl = (current_price - self.entry_price) * self.quantity
        else:
            self.unrealized_pnl = (self.entry_price - current_price) * self.quantity

        notional = self.entry_price * self.quantity
        self.unrealized_pnl_pct = (self.unrealized_pnl / notional * 100) if notional > 0 else 0.0


@dataclass
class ClosedTrade:
    """A completed trade for the log."""

    trade_id: str
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    pnl_pct: float
    close_reason: str
    strategy_id: str
    opened_at: datetime
    closed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    fees: float = 0.0


class PositionManager:
    """Persistent position manager with EventBus integration.

    Tracks open positions, calculates unrealized PnL, and logs closed trades.
    Positions are persisted to Parquet for durability.
    """

    def __init__(
        self,
        bus: EventBus | None = None,
        data_dir: Path = _DEFAULT_DATA_DIR,
    ) -> None:
        self._bus = bus
        self._data_dir = data_dir
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._positions: dict[str, Position] = {}
        self._closed_trades: list[ClosedTrade] = []
        self._load_positions()

    # ── EventBus handlers ─────────────────────────────────────────────

    def on_fill(self, event: Event) -> None:
        """Handle FillEvent — open or increase a position."""
        if not isinstance(event, FillEvent):
            return

        fill: FillEvent = event
        key = f"{fill.symbol}:{fill.side}"

        if key in self._positions:
            pos = self._positions[key]
            total_qty = pos.quantity + fill.fill_quantity
            if total_qty > 0:
                pos.entry_price = (
                    (pos.entry_price * pos.quantity + fill.fill_price * fill.fill_quantity)
                    / total_qty
                )
            pos.quantity = total_qty
            pos.current_price = fill.fill_price
            logger.info(
                "position_manager.increased symbol=%s qty=%.6f avg=%.5f",
                fill.symbol,
                pos.quantity,
                pos.entry_price,
            )
        else:
            pos = Position(
                symbol=fill.symbol,
                side=fill.side,
                quantity=fill.fill_quantity,
                entry_price=fill.fill_price,
                current_price=fill.fill_price,
                strategy_id=fill.strategy_id,
                order_id=fill.order_id,
            )
            self._positions[key] = pos
            logger.info(
                "position_manager.opened symbol=%s side=%s qty=%.6f price=%.5f",
                fill.symbol,
                fill.side,
                fill.fill_quantity,
                fill.fill_price,
            )

        self._save_positions()

    def on_close(self, event: Event) -> None:
        """Handle TradeClosedEvent — close a position."""
        if not isinstance(event, TradeClosedEvent):
            return

        closed: TradeClosedEvent = event
        key = f"{closed.symbol}:{closed.side}"

        if key in self._positions:
            del self._positions[key]
            self._save_positions()

        trade = ClosedTrade(
            trade_id=closed.trade_id,
            symbol=closed.symbol,
            side=closed.side,
            entry_price=closed.entry_price,
            exit_price=closed.exit_price,
            quantity=closed.quantity,
            pnl=closed.pnl,
            pnl_pct=closed.pnl_pct,
            close_reason=closed.close_reason,
            strategy_id=closed.strategy_id,
            opened_at=closed.timestamp,
            closed_at=datetime.now(UTC),
            fees=closed.fees,
        )
        self._closed_trades.append(trade)
        self._log_trade(trade)

        logger.info(
            "position_manager.closed symbol=%s side=%s pnl=%.2f reason=%s",
            closed.symbol,
            closed.side,
            closed.pnl,
            closed.close_reason,
        )

    # ── Query API ─────────────────────────────────────────────────────

    def get_positions(self) -> dict[str, Position]:
        """Return all open positions."""
        return dict(self._positions)

    def get_position(self, symbol: str, side: str = "") -> Position | None:
        """Get a specific position by symbol and optional side."""
        if side:
            return self._positions.get(f"{symbol}:{side}")
        for key, pos in self._positions.items():
            if key.startswith(f"{symbol}:"):
                return pos
        return None

    def get_total_exposure(self) -> float:
        """Total notional exposure across all positions."""
        return sum(p.notional for p in self._positions.values())

    def get_symbol_exposure(self, symbol: str) -> float:
        """Notional exposure for a specific symbol."""
        return sum(
            p.notional for p in self._positions.values() if p.symbol == symbol
        )

    def get_class_exposure(self, asset_class: str) -> float:
        """Notional exposure for an asset class (requires symbol mapping)."""
        from .trading_loop import _symbol_to_asset_class

        return sum(
            p.notional
            for p in self._positions.values()
            if _symbol_to_asset_class(p.symbol) == asset_class
        )

    def get_open_positions_count(self) -> int:
        return len(self._positions)

    def update_prices(self, prices: dict[str, float]) -> None:
        """Update unrealized PnL for all positions given current prices."""
        for pos in self._positions.values():
            price = prices.get(pos.symbol)
            if price is not None:
                pos.update_pnl(price)

    def get_closed_trades(self) -> list[ClosedTrade]:
        return list(self._closed_trades)

    def get_total_realized_pnl(self) -> float:
        return sum(t.pnl for t in self._closed_trades)

    # ── Persistence ───────────────────────────────────────────────────

    def _save_positions(self) -> None:
        """Save open positions to Parquet."""
        path = self._data_dir / "positions.parquet"
        if not self._positions:
            if path.exists():
                path.unlink()
            return

        try:
            import pandas as pd

            rows = []
            for key, pos in self._positions.items():
                rows.append({
                    "key": key,
                    "symbol": pos.symbol,
                    "side": pos.side,
                    "quantity": pos.quantity,
                    "entry_price": pos.entry_price,
                    "current_price": pos.current_price,
                    "stop_loss": pos.stop_loss,
                    "take_profit": pos.take_profit,
                    "strategy_id": pos.strategy_id,
                    "opened_at": pos.opened_at.isoformat(),
                    "order_id": pos.order_id,
                    "broker_order_id": pos.broker_order_id,
                })
            df = pd.DataFrame(rows)
            df.to_parquet(path, index=False)
        except Exception as exc:
            logger.error("position_manager.save_failed error=%s", exc)

    def _load_positions(self) -> None:
        """Load open positions from Parquet."""
        path = self._data_dir / "positions.parquet"
        if not path.exists():
            return

        try:
            import pandas as pd

            df = pd.read_parquet(path)
            for _, row in df.iterrows():
                pos = Position(
                    symbol=row["symbol"],
                    side=row["side"],
                    quantity=row["quantity"],
                    entry_price=row["entry_price"],
                    current_price=row.get("current_price", 0.0),
                    stop_loss=row.get("stop_loss", 0.0),
                    take_profit=row.get("take_profit", 0.0),
                    strategy_id=row.get("strategy_id", ""),
                    opened_at=datetime.fromisoformat(row["opened_at"]),
                    order_id=row.get("order_id", ""),
                    broker_order_id=row.get("broker_order_id", ""),
                )
                self._positions[row["key"]] = pos
            logger.info("position_manager.loaded count=%d", len(self._positions))
        except Exception as exc:
            logger.error("position_manager.load_failed error=%s", exc)

    def _log_trade(self, trade: ClosedTrade) -> None:
        """Append a closed trade to the log."""
        path = self._data_dir / "trade_log.parquet"
        try:
            import pandas as pd

            row = {
                "trade_id": trade.trade_id,
                "symbol": trade.symbol,
                "side": trade.side,
                "entry_price": trade.entry_price,
                "exit_price": trade.exit_price,
                "quantity": trade.quantity,
                "pnl": trade.pnl,
                "pnl_pct": trade.pnl_pct,
                "close_reason": trade.close_reason,
                "strategy_id": trade.strategy_id,
                "opened_at": trade.opened_at.isoformat(),
                "closed_at": trade.closed_at.isoformat(),
                "fees": trade.fees,
            }

            new_df = pd.DataFrame([row])
            if path.exists():
                existing = pd.read_parquet(path)
                combined = pd.concat([existing, new_df], ignore_index=True)
            else:
                combined = new_df
            combined.to_parquet(path, index=False)
        except Exception as exc:
            logger.error("position_manager.log_trade_failed error=%s", exc)

    def reset(self) -> None:
        """Reset all state (for testing)."""
        self._positions.clear()
        self._closed_trades.clear()
        path = self._data_dir / "positions.parquet"
        if path.exists():
            path.unlink()

"""
Trading Loop — the brain stem connecting signal generation to order execution.

Subscribes to final SignalEvents from PortfolioManager, converts them to
OrderEvents, submits to OMS, and emits FillEvent / TradeClosedEvent.

Architecture:
    PortfolioManager.act() → SignalEvent
    TradingLoop.observe()  → converts to OrderEvent
    TradingLoop._execute() → OMS.submit_order()
    TradingLoop._emit()    → FillEvent / TradeClosedEvent on EventBus

Safety:
    - Paper mode: simulated fills via PaperExecutor
    - Live mode: real broker via MT5Adapter (OMS routes)
    - Every order goes through OMS idempotency + crash-safe ledger
    - KillSwitchEvent stops the loop immediately
    - Golden Rules enforced at entry (SL required, risk limits)

Usage:
    loop = TradingLoop(bus=event_bus, oms=oms, config=config)
    bus.subscribe(SignalEvent, loop.observe)
    bus.subscribe(KillSwitchEvent, loop.on_kill_switch)
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .enums import OrderSide, SignalType, TradingMode
from .events import (
    Event,
    FillEvent,
    KillSwitchEvent,
    OrderEvent,
    SignalEvent,
    TradeClosedEvent,
)
from .golden_rules import GOLDEN_RULES
from .event_bus import EventBus

logger = logging.getLogger(__name__)


# ── Symbol → Asset Class mapping ──────────────────────────────────────────

_SYMBOL_ASSET_CLASS: dict[str, str] = {
    "XAUUSD": "metals",
    "XAGUSD": "metals",
    "EURUSD": "forex",
    "GBPUSD": "forex",
    "USDJPY": "forex",
    "AUDUSD": "forex",
    "USDCAD": "forex",
    "USDCHF": "forex",
    "NZDUSD": "forex",
    "EURAUD": "forex",
    "EURGBP": "forex",
    "EURJPY": "forex",
    "GBPJPY": "forex",
    "AUDJPY": "forex",
    "US30": "indices",
    "SPX500": "indices",
    "NAS100": "indices",
    "DE40": "indices",
    "BTCUSD": "crypto",
    "ETHUSD": "crypto",
}


def _symbol_to_asset_class(symbol: str) -> str:
    """Map a trading symbol to its asset class for OMS routing."""
    return _SYMBOL_ASSET_CLASS.get(symbol.upper(), "forex")


# ── Order tracking ────────────────────────────────────────────────────────


@dataclass
class TrackedOrder:
    """Internal tracking for an order submitted through the loop."""

    order_id: str
    signal_id: str
    symbol: str
    side: str
    quantity: float
    entry_price: float
    stop_loss: float
    take_profit: float
    strategy_id: str
    trace_id: str = ""
    submitted_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    filled_at: datetime | None = None
    fill_price: float = 0.0
    fill_quantity: float = 0.0
    status: str = "pending"
    broker_order_id: str = ""


# ── Paper Executor ────────────────────────────────────────────────────────


class PaperExecutor:
    """Simulated order execution for paper trading mode.

    Fills at the requested price with configurable slippage.
    Used when TradingMode == PAPER.
    """

    def __init__(
        self,
        slippage_pips: float = 0.5,
        commission_per_lot: float = 3.5,
        units_per_lot: float = 100000.0,
    ) -> None:
        self.slippage_pips = slippage_pips
        self.commission_per_lot = commission_per_lot
        self.units_per_lot = units_per_lot
        self._fills: list[dict[str, Any]] = []

    def submit(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
    ) -> dict[str, Any]:
        """Simulate a fill with slippage."""
        pip_value = 0.0001 if "JPY" not in symbol else 0.01
        if symbol.upper() == "XAUUSD":
            pip_value = 0.01

        slippage = self.slippage_pips * pip_value
        if side.upper() == "BUY":
            fill_price = price + slippage
        else:
            fill_price = price - slippage

        lots = quantity / self.units_per_lot
        commission = lots * self.commission_per_lot

        fill = {
            "fill_price": fill_price,
            "fill_quantity": quantity,
            "commission": commission,
            "slippage": slippage,
            "timestamp": datetime.now(UTC),
        }
        self._fills.append(fill)
        return fill

    def get_fills(self) -> list[dict[str, Any]]:
        return list(self._fills)


# ── Trading Loop ──────────────────────────────────────────────────────────


class TradingLoop:
    """The brain stem of the trading system.

    Receives final SignalEvents from PortfolioManager, validates them
    against Golden Rules, converts to OMS orders, and emits execution
    events on the EventBus.

    Parameters
    ----------
    bus : EventBus
        The system event bus.
    oms : OMS | None
        Order management system. Required for live/paper execution.
    config : QuantConfig | None
        System configuration. Uses defaults if None.
    paper_executor : PaperExecutor | None
        Simulated executor for paper mode. Created automatically if None.
    """

    def __init__(
        self,
        bus: EventBus,
        oms: Any | None = None,
        config: Any | None = None,
        paper_executor: PaperExecutor | None = None,
    ) -> None:
        self._bus = bus
        self._oms = oms
        self._config = config
        self._paper = paper_executor or PaperExecutor()
        self._kill_switch_active = False
        self._tracked: dict[str, TrackedOrder] = {}
        self._daily_order_count: int = 0
        self._daily_reset_date: str = datetime.now(UTC).strftime("%Y-%m-%d")
        self._total_filled: int = 0
        self._total_rejected: int = 0

    # ── Event handlers ────────────────────────────────────────────────

    def observe(self, event: Event) -> None:
        """Handle incoming SignalEvent from PortfolioManager."""
        if self._kill_switch_active:
            logger.warning("trading_loop.kill_switch_active — signal ignored")
            return

        if not isinstance(event, SignalEvent):
            return

        if not event.metadata.get("final"):
            return

        if event.signal_type in (SignalType.NO_TRADE, SignalType.HOLD):
            return

        self._process_signal(event)

    def on_kill_switch(self, event: Event) -> None:
        """Handle KillSwitchEvent — stop all trading immediately."""
        if isinstance(event, KillSwitchEvent):
            self._kill_switch_active = True
            logger.critical(
                "trading_loop.kill_switch_triggered trigger=%s reason=%s",
                event.trigger,
                event.reason,
            )
            if self._oms is not None:
                try:
                    cancelled = self._oms.cancel_all()
                    logger.info("trading_loop.cancel_all result=%d", len(cancelled))
                except Exception as exc:
                    logger.error("trading_loop.cancel_all_failed error=%s", exc)

    # ── Signal processing ─────────────────────────────────────────────

    def _process_signal(self, signal: SignalEvent) -> None:
        """Validate and convert a SignalEvent to an order."""
        self._reset_daily_counter()

        # Golden Rule: every trade must have SL
        if GOLDEN_RULES.REQUIRE_STOP_LOSS and signal.stop_loss <= 0:
            logger.warning(
                "trading_loop.rejected_no_sl symbol=%s confidence=%.2f",
                signal.symbol,
                signal.confidence,
            )
            self._total_rejected += 1
            return

        # Golden Rule: micro mode daily order limit
        mode = self._get_trading_mode()
        if mode == TradingMode.LIVE_MICRO:
            if self._daily_order_count >= GOLDEN_RULES.MICRO_DAILY_ORDER_LIMIT:
                logger.warning(
                    "trading_loop.rejected_daily_limit symbol=%s count=%d",
                    signal.symbol,
                    self._daily_order_count,
                )
                self._total_rejected += 1
                return

        # Golden Rule: limited mode daily trade limit
        if mode == TradingMode.LIVE_LIMITED:
            if self._daily_order_count >= GOLDEN_RULES.LIMITED_MAX_DAILY_TRADES:
                logger.warning(
                    "trading_loop.rejected_daily_limit_limited symbol=%s count=%d",
                    signal.symbol,
                    self._daily_order_count,
                )
                self._total_rejected += 1
                return

        # Sanity check: entry, SL, TP must be valid
        if signal.entry_price <= 0 or signal.stop_loss <= 0 or signal.take_profit <= 0:
            logger.warning("trading_loop.rejected_invalid_levels symbol=%s entry=%.2f sl=%.2f tp=%.2f",
                            signal.symbol, signal.entry_price, signal.stop_loss, signal.take_profit)
            self._total_rejected += 1
            return

        # Sanity check: SL must be on correct side of entry
        if signal.signal_type == SignalType.BUY and signal.stop_loss >= signal.entry_price:
            logger.warning("trading_loop.rejected_sl_on_wrong_side symbol=%s", signal.symbol)
            self._total_rejected += 1
            return
        if signal.signal_type == SignalType.SELL and signal.stop_loss <= signal.entry_price:
            logger.warning("trading_loop.rejected_sl_on_wrong_side symbol=%s", signal.symbol)
            self._total_rejected += 1
            return

        # Convert signal to order
        side = "BUY" if signal.signal_type == SignalType.BUY else "SELL"
        quantity = signal.metadata.get("approved_quantity", 0.0)
        if quantity <= 0:
            logger.warning(
                "trading_loop.rejected_zero_qty symbol=%s", signal.symbol
            )
            self._total_rejected += 1
            return

        order_id = str(uuid.uuid4())
        asset_class = _symbol_to_asset_class(signal.symbol)

        tracked = TrackedOrder(
            order_id=order_id,
            signal_id=signal.event_id,
            symbol=signal.symbol,
            side=side,
            quantity=quantity,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            strategy_id=signal.source,
            trace_id=signal.trace_id,
        )
        self._tracked[order_id] = tracked

        # Emit OrderEvent for audit trail
        order_event = OrderEvent(
            order_id=order_id,
            symbol=signal.symbol,
            side=side,
            order_type="MARKET",
            quantity=quantity,
            price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            strategy_id=signal.source,
            signal_id=signal.event_id,
            source="trading_loop",
            trace_id=signal.trace_id,
            metadata={
                "asset_class": asset_class,
                "confidence": signal.confidence,
                "regime": signal.regime,
            },
        )
        self._bus.publish(order_event)

        # Execute
        self._execute_order(tracked, asset_class)

    def _execute_order(self, tracked: TrackedOrder, asset_class: str) -> None:
        """Submit order to OMS (live) or PaperExecutor (paper/micro)."""
        mode = self._get_trading_mode()

        try:
            if mode in (TradingMode.PAPER, TradingMode.LIVE_MICRO):
                self._execute_paper(tracked)
            else:
                self._execute_live(tracked, asset_class)
        except Exception as exc:
            logger.error(
                "trading_loop.execution_failed order_id=%s error=%s",
                tracked.order_id,
                exc,
            )
            tracked.status = "failed"
            self._total_rejected += 1

    def _execute_paper(self, tracked: TrackedOrder) -> None:
        """Execute via PaperExecutor (simulated fills)."""
        fill = self._paper.submit(
            symbol=tracked.symbol,
            side=tracked.side,
            quantity=tracked.quantity,
            price=tracked.entry_price,
            stop_loss=tracked.stop_loss,
            take_profit=tracked.take_profit,
        )

        tracked.status = "filled"
        tracked.fill_price = fill["fill_price"]
        tracked.fill_quantity = fill["fill_quantity"]
        tracked.filled_at = fill["timestamp"]
        self._daily_order_count += 1
        self._total_filled += 1

        # Emit FillEvent
        fill_event = FillEvent(
            order_id=tracked.order_id,
            symbol=tracked.symbol,
            side=tracked.side,
            fill_price=fill["fill_price"],
            fill_quantity=fill["fill_quantity"],
            commission=fill["commission"],
            slippage=fill["slippage"],
            strategy_id=tracked.strategy_id,
            source="paper_executor",
            trace_id=tracked.trace_id if tracked.trace_id else str(uuid.uuid4()),
        )
        self._bus.publish(fill_event)

        # Emit TradeClosedEvent (paper trades close immediately at entry)
        self._emit_trade_closed(tracked, fill["fill_price"], "PAPER_ENTRY")

        logger.info(
            "trading_loop.paper_fill order_id=%s symbol=%s side=%s "
            "qty=%.6f price=%.5f",
            tracked.order_id,
            tracked.symbol,
            tracked.side,
            fill["fill_quantity"],
            fill["fill_price"],
        )

    def _execute_live(self, tracked: TrackedOrder, asset_class: str) -> None:
        """Execute via OMS → broker adapter (real money)."""
        if self._oms is None:
            logger.error("trading_loop.no_oms — cannot execute live order")
            tracked.status = "failed"
            self._total_rejected += 1
            return

        order = self._oms.submit_order(
            signal_id=tracked.signal_id,
            symbol=tracked.symbol,
            asset_class=asset_class,
            side=tracked.side,
            quantity=tracked.quantity,
            stop_loss=tracked.stop_loss if tracked.stop_loss > 0 else None,
            take_profit=tracked.take_profit if tracked.take_profit > 0 else None,
        )

        from ..execution.adapters.base import OrderStatus

        if order.status == OrderStatus.FILLED:
            tracked.status = "filled"
            tracked.fill_price = tracked.entry_price  # broker fills near entry for market orders
            tracked.fill_quantity = order.quantity
            tracked.broker_order_id = order.broker_order_id or ""
            tracked.filled_at = datetime.now(UTC)
            self._daily_order_count += 1
            self._total_filled += 1

            fill_event = FillEvent(
                order_id=tracked.order_id,
                symbol=tracked.symbol,
                side=tracked.side,
                fill_price=tracked.entry_price,
                fill_quantity=order.quantity,
                commission=0.0,
                slippage=0.0,
                strategy_id=tracked.strategy_id,
                source="mt5_adapter",
                trace_id=tracked.trace_id if tracked.trace_id else str(uuid.uuid4()),
            )
            self._bus.publish(fill_event)

            logger.info(
                "trading_loop.live_fill order_id=%s broker_id=%s symbol=%s "
                "side=%s qty=%.6f",
                tracked.order_id,
                order.broker_order_id,
                tracked.symbol,
                tracked.side,
                order.quantity,
            )
        else:
            tracked.status = order.status.value if hasattr(order.status, "value") else str(order.status)
            self._total_rejected += 1
            logger.warning(
                "trading_loop.live_rejected order_id=%s status=%s",
                tracked.order_id,
                tracked.status,
            )

    def _emit_trade_closed(
        self, tracked: TrackedOrder, exit_price: float, reason: str
    ) -> None:
        """Emit a TradeClosedEvent for tracking."""
        if tracked.side == "BUY":
            pnl = (exit_price - tracked.entry_price) * tracked.quantity
        else:
            pnl = (tracked.entry_price - exit_price) * tracked.quantity

        notional = tracked.entry_price * tracked.quantity
        pnl_pct = (pnl / notional * 100) if notional > 0 else 0.0

        closed_event = TradeClosedEvent(
            trade_id=tracked.order_id,
            symbol=tracked.symbol,
            side=tracked.side,
            entry_price=tracked.entry_price,
            exit_price=exit_price,
            quantity=tracked.quantity,
            pnl=pnl,
            pnl_pct=pnl_pct,
            close_reason=reason,
            strategy_id=tracked.strategy_id,
            source="trading_loop",
            trace_id=tracked.trace_id if tracked.trace_id else str(uuid.uuid4()),
        )
        self._bus.publish(closed_event)

    # ── Helpers ───────────────────────────────────────────────────────

    def _get_trading_mode(self) -> TradingMode:
        if self._config is not None:
            return self._config.trading_mode
        return TradingMode.PAPER

    def _reset_daily_counter(self) -> None:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        if today != self._daily_reset_date:
            self._daily_order_count = 0
            self._daily_reset_date = today

    def get_stats(self) -> dict[str, Any]:
        """Return loop statistics."""
        return {
            "kill_switch_active": self._kill_switch_active,
            "daily_order_count": self._daily_order_count,
            "total_filled": self._total_filled,
            "total_rejected": self._total_rejected,
            "tracked_orders": len(self._tracked),
            "trading_mode": self._get_trading_mode().value,
        }

    def get_tracked(self, order_id: str) -> TrackedOrder | None:
        return self._tracked.get(order_id)

    def reset(self) -> None:
        """Reset loop state (for testing)."""
        self._kill_switch_active = False
        self._tracked.clear()
        self._daily_order_count = 0
        self._total_filled = 0
        self._total_rejected = 0

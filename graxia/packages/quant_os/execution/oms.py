"""Order Management System – multi-venue router with idempotency, crash safety, and state machine."""

import contextlib
import json
import logging
import os
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .adapters.base import (
    AccountInfo,
    BrokerAdapter,
    Order,
    OrderStatus,
)
from .order_state_machine import OrderStateMachine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Trailing / fixed stop-loss configuration
# ---------------------------------------------------------------------------


@dataclass
class TrailingStopConfig:
    """Configuration for post-fill stop-loss behaviour per asset class or symbol."""

    enabled: bool = True
    trail_multiplier: float = 2.0  # ATR multiplier for SL distance
    stop_mode: str = "trailing"  # "trailing" | "fixed"


# ---------------------------------------------------------------------------
# Per-symbol stop-loss configuration (research-optimised multipliers)
# ---------------------------------------------------------------------------

_SYMBOL_STOP_CONFIGS: dict[str, TrailingStopConfig] = {
    "XAUUSD": TrailingStopConfig(enabled=True, trail_multiplier=2.5, stop_mode="fixed"),
    "NAS100": TrailingStopConfig(enabled=True, trail_multiplier=2.0, stop_mode="fixed"),
    "US100": TrailingStopConfig(enabled=True, trail_multiplier=2.0, stop_mode="fixed"),
    "USTEC": TrailingStopConfig(enabled=True, trail_multiplier=2.0, stop_mode="fixed"),
    "USOIL": TrailingStopConfig(enabled=True, trail_multiplier=3.0, stop_mode="fixed"),
    "USDJPY": TrailingStopConfig(enabled=True, trail_multiplier=1.5, stop_mode="fixed"),
}

# ---------------------------------------------------------------------------
# Default per-asset-class stop configuration
# ---------------------------------------------------------------------------

_DEFAULT_TRAILING_CONFIGS: dict[str, TrailingStopConfig] = {
    "metals": TrailingStopConfig(enabled=True, trail_multiplier=2.5, stop_mode="fixed"),
    "forex": TrailingStopConfig(enabled=True, trail_multiplier=2.0, stop_mode="fixed"),
    "indices": TrailingStopConfig(enabled=True, trail_multiplier=2.0, stop_mode="fixed"),
    "crypto": TrailingStopConfig(enabled=True, trail_multiplier=2.0, stop_mode="trailing"),
}

# ---------------------------------------------------------------------------
# Venue routing table
# ---------------------------------------------------------------------------
VENUE_MAP: dict[str, str] = {
    "metals": "mt5",
    "forex": "mt5",
    "indices": "mt5",
    "crypto": "mt5",
}

# Partial-fill timeout (seconds)
_FILL_TIMEOUT = 30.0

# Auto-compact when ledger exceeds this many lines
COMPACT_THRESHOLD = 10_000

# Ledger path (JSONL – one record per order)
_DEFAULT_LEDGER = Path("data/execution_ledger.jsonl")


class OMS:
    """Order Management System with multi-venue routing.

    Responsibilities:
    * Route orders to the correct broker adapter by ``asset_class``.
    * Enforce full idempotency: a ``signal_id`` already present in the ledger
      is never submitted a second time.
    * Persist to the ledger **before** contacting the broker (crash safety).
    * Handle partial fills with a configurable timeout.
    * Provide ``cancel_all`` as a kill-switch.
    """

    def __init__(
        self,
        adapters: dict[str, BrokerAdapter],
        ledger_path: Path = _DEFAULT_LEDGER,
        risk_engine: Any = None,
        trailing_stop_configs: dict[str, TrailingStopConfig] | None = None,
        symbol_stop_configs: dict[str, TrailingStopConfig] | None = None,
    ) -> None:
        self._adapters = adapters
        self._ledger_path = ledger_path
        self._ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self._orders: dict[str, Order] = {}
        self._orders_by_signal_id: dict[str, Order] = {}
        self._state_machines: dict[str, OrderStateMachine] = {}
        self._risk_engine = risk_engine
        self._trailing_stop_configs = trailing_stop_configs or dict(_DEFAULT_TRAILING_CONFIGS)
        self._symbol_stop_configs = symbol_stop_configs or dict(_SYMBOL_STOP_CONFIGS)
        self._load_ledger()
        # Auto-compact on startup if ledger exceeds threshold
        if self._line_count() > COMPACT_THRESHOLD:
            self.compact_ledger()

    # ------------------------------------------------------------------
    # Ledger helpers
    # ------------------------------------------------------------------

    def _load_ledger(self) -> None:
        """Replay ALL events from the ledger to reconstruct full status history per order."""
        if not self._ledger_path.exists():
            return
        events_by_order: dict[str, list[dict]] = {}
        with open(self._ledger_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                oid = record["order_id"]
                events_by_order.setdefault(oid, []).append(record)
        for oid, events in events_by_order.items():
            first = events[0]
            order = Order(
                order_id=oid,
                signal_id=first["signal_id"],
                symbol=first["symbol"],
                asset_class=first["asset_class"],
                side=first["side"],
                quantity=first["quantity"],
                stop_loss=first.get("stop_loss"),
                take_profit=first.get("take_profit"),
                status=OrderStatus(first["status"]),
                broker_order_id=first.get("broker_order_id"),
                created_at=datetime.fromisoformat(first["created_at"]),
            )
            sm = OrderStateMachine(order_id=oid, initial=OrderStatus.SIGNAL_CREATED)
            for evt in events[1:]:
                target = OrderStatus(evt["status"])
                with contextlib.suppress(Exception):
                    sm.advance(target, f"replay: {target.value}")
                order.status = target
                if evt.get("broker_order_id"):
                    order.broker_order_id = evt["broker_order_id"]
            self._orders[oid] = order
            if order.signal_id:
                self._orders_by_signal_id[order.signal_id] = order
            self._state_machines[oid] = sm
        logger.info(
            "Ledger loaded: %d orders replayed across %d events",
            len(self._orders),
            sum(len(v) for v in events_by_order.values()),
        )

    def _update_ledger(self, order: Order) -> None:
        """Append status update to the JSONL ledger (event sourcing)."""
        record = {
            "order_id": order.order_id,
            "signal_id": order.signal_id,
            "symbol": order.symbol,
            "asset_class": order.asset_class,
            "side": order.side,
            "quantity": order.quantity,
            "stop_loss": order.stop_loss,
            "take_profit": order.take_profit,
            "status": order.status.value,
            "broker_order_id": order.broker_order_id,
            "created_at": order.created_at.isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        with open(self._ledger_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

    # ------------------------------------------------------------------
    # Ledger compaction
    # ------------------------------------------------------------------

    def _line_count(self) -> int:
        """Return the number of lines in the ledger file."""
        if not self._ledger_path.exists():
            return 0
        count = 0
        with open(self._ledger_path, encoding="utf-8") as fh:
            for _ in fh:
                count += 1
        return count

    def compact_ledger(self, max_age_days: int = 30) -> bool:
        """Compact the JSONL ledger: deduplicate by order_id, drop old entries.

        Steps:
        1. Read all lines, deduplicate by order_id (keep latest per order).
        2. Drop orders older than ``max_age_days``.
        3. Write to a temp file, then atomically ``os.replace`` into place.

        Returns True if compaction happened, False otherwise.
        """
        if not self._ledger_path.exists():
            return False

        cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
        latest_by_order: dict[str, dict] = {}

        with open(self._ledger_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                oid = record["order_id"]
                latest_by_order[oid] = record

        if not latest_by_order:
            return False

        # Filter out old orders
        kept: list[dict] = []
        for _oid, rec in latest_by_order.items():
            created = rec.get("created_at") or rec.get("updated_at")
            if created:
                try:
                    ts = datetime.fromisoformat(created)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=UTC)
                    if ts < cutoff:
                        continue
                except (ValueError, TypeError):
                    pass
            kept.append(rec)

        if not kept:
            # Write empty ledger atomically
            fd, tmp_path = tempfile.mkstemp(
                suffix=".jsonl",
                dir=str(self._ledger_path.parent),
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    pass  # empty file
                os.replace(tmp_path, str(self._ledger_path))
            except Exception:
                os.unlink(tmp_path)
                raise
            logger.info("Ledger compacted: all orders expired, ledger emptied")
            return True

        # Sort by created_at for clean ordering
        kept.sort(key=lambda r: r.get("created_at") or r.get("updated_at") or "")

        # Atomic write via tempfile + os.replace
        fd, tmp_path = tempfile.mkstemp(
            suffix=".jsonl",
            dir=str(self._ledger_path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                for rec in kept:
                    fh.write(json.dumps(rec) + "\n")
            os.replace(tmp_path, str(self._ledger_path))
        except Exception:
            os.unlink(tmp_path)
            raise

        logger.info(
            "Ledger compacted: %d orders retained (max_age=%d days)",
            len(kept),
            max_age_days,
        )
        return True

    # ------------------------------------------------------------------
    # Idempotency check
    # ------------------------------------------------------------------

    def _find_by_signal_id(self, signal_id: str) -> Order | None:
        """Return the order matching *signal_id*, if any (O(1) via secondary index)."""
        return self._orders_by_signal_id.get(signal_id)

    # ------------------------------------------------------------------
    # Adapter lookup
    # ------------------------------------------------------------------

    def _get_adapter(self, asset_class: str) -> BrokerAdapter:
        """Resolve the adapter for a given asset class."""
        venue = VENUE_MAP.get(asset_class.lower())
        if venue is None:
            raise ValueError(f"No venue mapped for asset_class={asset_class!r}. " f"Known: {list(VENUE_MAP)}")
        adapter = self._adapters.get(venue)
        if adapter is None:
            raise RuntimeError(f"Adapter {venue!r} not registered")
        return adapter

    def _ensure_connected(self, adapter: BrokerAdapter) -> None:
        """Use the unified connection lifecycle before any broker call."""
        if not adapter.is_connected:
            adapter.connect()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit_order(
        self,
        signal_id: str,
        symbol: str,
        asset_class: str,
        side: str,
        quantity: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        trace_id: str = "",
    ) -> Order:
        """Submit an order with full idempotency, crash safety, and state machine.

        Steps:
        1. Check ledger for an existing order with the same ``signal_id``.
           If found, return it (no duplicate submission).
        2. Create the ``Order``, persist to ledger **before** contacting broker.
        3. Route to the correct adapter.
        4. Handle partial fills with a 30-second timeout.
        5. Update ledger with final status.

        Returns:
            The ``Order`` object with final status and broker metadata.
        """
        # --- Idempotency guard ---
        existing = self._find_by_signal_id(signal_id)
        if existing is not None:
            logger.info(
                "Signal %s already in ledger (order %s, status %s) – skipping",
                signal_id,
                existing.order_id,
                existing.status.value,
            )
            return existing

        # --- Build order ---
        order = Order(
            order_id=str(uuid.uuid4()),
            signal_id=signal_id,
            symbol=symbol,
            asset_class=asset_class,
            side=side,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
            status=OrderStatus.PENDING,
            trace_id=trace_id,
        )

        # --- Initialize state machine ---
        sm = OrderStateMachine(order_id=order.order_id, initial=OrderStatus.SIGNAL_CREATED)
        self._state_machines[order.order_id] = sm

        # --- Crash safety: persist BEFORE sending ---
        self._orders[order.order_id] = order
        if order.signal_id:
            self._orders_by_signal_id[order.signal_id] = order

        # --- State machine: SIGNAL_CREATED → RISK_CHECKED → ORDER_PRECHECKED ---
        try:
            sm.advance(OrderStatus.RISK_CHECKED, "pre-trade risk passed")
            sm.advance(OrderStatus.ORDER_PRECHECKED, "pre-checks passed")
        except Exception as exc:
            logger.error("oms.state_machine_error order_id=%s error=%s", order.order_id, exc)

        # --- Pre-trade risk gate (fail-closed) ---
        if self._risk_engine is not None:
            try:
                risk_result = self._risk_engine.check_order_sync(order)
                if not risk_result.passed:
                    order.status = OrderStatus.REJECTED
                    with contextlib.suppress(Exception):
                        sm.advance(OrderStatus.REJECTED, f"risk rejected: {risk_result.reason}")
                    self._update_ledger(order)
                    logger.warning(
                        "Order %s REJECTED by pre-trade risk: %s",
                        order.order_id,
                        risk_result.reason,
                    )
                    return order
            except Exception as exc:
                logger.error("oms.risk_check_error order_id=%s error=%s", order.order_id, exc)
                order.status = OrderStatus.REJECTED
                with contextlib.suppress(Exception):
                    sm.advance(OrderStatus.REJECTED, f"risk check error: {exc}")
                self._update_ledger(order)
                return order

        # --- Route & submit ---
        adapter = self._get_adapter(asset_class)
        self._ensure_connected(adapter)
        try:
            sm.advance(OrderStatus.ORDER_SUBMITTED, "sent to adapter")
        except Exception as exc:
            logger.error("oms.state_machine_error order_id=%s error=%s", order.order_id, exc)
        order.status = OrderStatus.SUBMITTED
        self._update_ledger(order)

        result = adapter.submit_order(order)

        # --- Handle result with state machine ---
        if result.status == OrderStatus.FILLED:
            try:
                sm.advance(OrderStatus.ORDER_ACKNOWLEDGED, "broker acknowledged")
                sm.advance(OrderStatus.FILLED, "fully filled")
            except Exception as exc:
                logger.error("oms.state_machine_error order_id=%s error=%s", order.order_id, exc)
            order.status = OrderStatus.FILLED
            order.quantity = result.filled_quantity  # type: ignore[assignment]
            logger.info(
                "Order %s filled: qty=%.6f avg=%.5f",
                order.order_id,
                result.filled_quantity,
                result.avg_price,
            )
        elif result.status == OrderStatus.PARTIALLY_FILLED:
            try:
                sm.advance(OrderStatus.ORDER_ACKNOWLEDGED, "broker acknowledged")
            except Exception as exc:
                logger.error("oms.state_machine_error order_id=%s error=%s", order.order_id, exc)
            order.status = OrderStatus.PARTIALLY_FILLED
            order.quantity = result.filled_quantity  # type: ignore[assignment]
            logger.warning(
                "Order %s partially filled: %.6f/%.6f – waiting up to %ds",
                order.order_id,
                result.filled_quantity,
                quantity,
                _FILL_TIMEOUT,
            )
            order = self._poll_fill(order, adapter, sm)
        elif result.status == OrderStatus.FAILED:
            try:
                sm.advance(OrderStatus.REJECTED, f"broker rejected: {result.error}")
            except Exception as exc:
                logger.error("oms.state_machine_error order_id=%s error=%s", order.order_id, exc)
            order.status = OrderStatus.FAILED
            logger.error("Order %s failed: %s", order.order_id, result.error)
        elif result.status == OrderStatus.TIMEOUT:
            try:
                sm.advance(OrderStatus.REJECTED, f"broker timeout: {result.error}")
            except Exception as exc:
                logger.error("oms.state_machine_error order_id=%s error=%s", order.order_id, exc)
            order.status = OrderStatus.TIMEOUT
            logger.error("Order %s timed out: %s", order.order_id, result.error)

        self._update_ledger(order)
        return order

    def _poll_fill(self, order: Order, adapter: BrokerAdapter, sm: OrderStateMachine | None = None) -> Order:
        """Poll broker until order is filled or timeout expires."""
        deadline = time.monotonic() + _FILL_TIMEOUT
        while time.monotonic() < deadline:
            time.sleep(2.0)
            if order.broker_order_id is None:
                break
            self._ensure_connected(adapter)
            status = adapter.get_order_status(order.broker_order_id)
            if status.status == OrderStatus.FILLED:
                if sm is not None:
                    sm.advance(OrderStatus.FILLED, "fully filled via poll")
                order.status = OrderStatus.FILLED
                order.quantity = status.filled_quantity  # type: ignore[assignment]
                return order
            if status.status in (OrderStatus.CANCELLED, OrderStatus.FAILED):
                if sm is not None:
                    sm.advance(OrderStatus.REJECTED, f"poll result: {status.status.value}")
                order.status = status.status
                return order
        # Timeout – mark as TIMEOUT
        if sm is not None:
            sm.advance(OrderStatus.REJECTED, "fill poll timeout")
        order.status = OrderStatus.TIMEOUT
        logger.warning("Order %s fill poll timed out", order.order_id)
        return order

    def cancel_all(self, asset_class: str | None = None) -> list[Order]:
        """Cancel every open order, optionally filtered by asset class.

        This serves as the **kill switch**.  It iterates all orders that are
        still in a cancellable state and issues a cancel to the relevant
        adapter.

        Returns:
            List of orders whose status was updated.
        """
        cancelled: list[Order] = []
        terminal = {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.FAILED, OrderStatus.TIMEOUT}

        for order in list(self._orders.values()):
            if order.status in terminal:
                continue
            if asset_class is not None and order.asset_class.lower() != asset_class.lower():
                continue

            try:
                adapter = self._get_adapter(order.asset_class)
                self._ensure_connected(adapter)
                if order.broker_order_id:
                    result = adapter.cancel_order(order.broker_order_id)
                    order.status = result.status
                else:
                    order.status = OrderStatus.CANCELLED
                cancelled.append(order)
            except Exception as exc:
                logger.error("Failed to cancel order %s: %s", order.order_id, exc)
                order.status = OrderStatus.FAILED

        if cancelled:
            for order in cancelled:
                self._update_ledger(order)
            logger.info("Kill switch: cancelled %d orders", len(cancelled))

        return cancelled

    def close_position(
        self,
        symbol: str,
        broker_position_id: str,
        volume: float,
        asset_class: str = "forex",
        signal_id: str = "",
    ) -> Order:
        """Close an open position via the broker adapter.

        Args:
            symbol: MT5 symbol name.
            broker_position_id: MT5 position ticket as string.
            volume: Position volume (lots).
            asset_class: Asset class for adapter routing.
            signal_id: Signal ID for tracking.

        Returns:
            Order with status FILLED or FAILED.
        """
        adapter = self._get_adapter(asset_class)
        self._ensure_connected(adapter)
        try:
            result = adapter.close_position(
                broker_position_id=broker_position_id,
                volume=volume,
                symbol=symbol,
            )
            # Create an Order to track this close
            order = Order(
                order_id=f"close-{broker_position_id}",
                signal_id=signal_id,
                symbol=symbol,
                asset_class=asset_class,
                side="SELL" if volume > 0 else "BUY",
                quantity=abs(volume),
            )
            order.status = result.status
            order.broker_order_id = result.broker_id
            if result.status == OrderStatus.FILLED:
                logger.info("Closed position %s %s: filled", symbol, broker_position_id)
            else:
                logger.warning("Failed to close position %s %s: %s", symbol, broker_position_id, result)
            return order
        except Exception as exc:
            logger.error("Error closing position %s %s: %s", symbol, broker_position_id, exc)
            order = Order(
                order_id=f"close-{broker_position_id}",
                signal_id=signal_id,
                symbol=symbol,
                asset_class=asset_class,
                side="SELL" if volume > 0 else "BUY",
                quantity=abs(volume),
            )
            order.status = OrderStatus.FAILED
            return order

    # ------------------------------------------------------------------
    # Post-fill stop-loss setup
    # ------------------------------------------------------------------

    def _setup_post_fill_stop_loss(
        self,
        order: Order,
        avg_price: float,
        adapter: BrokerAdapter,
    ) -> None:
        """Set stop-loss on a freshly-filled position.

        Logic:
        1. Skip if order already has ``stop_loss`` set.
        2. Find the matching position by ``order_id`` in the comment field.
        3. Resolve config: symbol override → asset-class default.
        4. If disabled, skip.
        5. Compute SL from ATR proxy (2 % of fill price) × multiplier.
        """
        if order.stop_loss is not None:
            return

        # Find the position that matches this order
        positions = adapter.get_positions()
        position = None
        for p in positions:
            if p.get("comment") == order.order_id:
                position = p
                break
        if position is None:
            return

        # Resolve config: symbol override takes priority
        symbol = position.get("symbol", order.symbol)
        cfg = self._symbol_stop_configs.get(symbol)
        if cfg is None:
            asset_class = order.asset_class.lower()
            cfg = self._trailing_stop_configs.get(asset_class)
        if cfg is None or not cfg.enabled:
            return

        # ATR proxy: 2 % of fill price (no real ATR pipeline yet)
        atr_proxy = avg_price * 0.02
        multiplier = cfg.trail_multiplier

        if order.side.upper() == "BUY":
            sl_price = avg_price - (atr_proxy * multiplier)
        else:
            sl_price = avg_price + (atr_proxy * multiplier)

        adapter.set_stop_loss(
            position_ticket=position["ticket"],
            symbol=symbol,
            stop_loss_price=round(sl_price, 5),
        )

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_account_info(self, venue: str) -> AccountInfo:
        """Fetch account info from a specific venue adapter."""
        adapter = self._adapters.get(venue)
        if adapter is None:
            raise RuntimeError(f"Adapter {venue!r} not registered")
        self._ensure_connected(adapter)
        return adapter.get_account_info()

    def get_positions(self, venue: str) -> list[dict]:
        """Fetch open positions from a specific venue adapter."""
        adapter = self._adapters.get(venue)
        if adapter is None:
            raise RuntimeError(f"Adapter {venue!r} not registered")
        self._ensure_connected(adapter)
        return adapter.get_positions()

    def order_by_id(self, order_id: str) -> Order | None:
        """Look up an order by its internal order_id."""
        return self._orders.get(order_id)

    def order_by_signal(self, signal_id: str) -> Order | None:
        """Look up an order by the originating signal_id."""
        return self._find_by_signal_id(signal_id)

    def get_state_machine(self, order_id: str) -> OrderStateMachine | None:
        """Return the state machine for a given order (for audit trail)."""
        return self._state_machines.get(order_id)

    def get_state_history(self, order_id: str) -> list[str]:
        """Return the state transition history for an order."""
        sm = self._state_machines.get(order_id)
        if sm is None:
            return []
        return [s.value for s in sm._history]

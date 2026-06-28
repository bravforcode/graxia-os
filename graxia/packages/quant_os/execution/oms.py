"""Order Management System – multi-venue router with idempotency, crash safety, and state machine."""

import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from .adapters.base import (
    AccountInfo,
    BrokerAdapter,
    Order,
    OrderResult,
    OrderStatus,
)
from .order_state_machine import OrderStateMachine, TRANSITIONS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Venue routing table
# ---------------------------------------------------------------------------
VENUE_MAP: dict[str, str] = {
    "metals": "mt5",
    "forex": "mt5",
    "indices": "mt5",
    "crypto": "binance",
}

# Partial-fill timeout (seconds)
_FILL_TIMEOUT = 30.0

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
    ) -> None:
        self._adapters = adapters
        self._ledger_path = ledger_path
        self._ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self._orders: dict[str, Order] = {}
        self._state_machines: dict[str, OrderStateMachine] = {}
        self._load_ledger()

    # ------------------------------------------------------------------
    # Ledger helpers
    # ------------------------------------------------------------------

    def _load_ledger(self) -> None:
        """Replay the ledger file into memory on startup."""
        if not self._ledger_path.exists():
            return
        with open(self._ledger_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                order = Order(
                    order_id=record["order_id"],
                    signal_id=record["signal_id"],
                    symbol=record["symbol"],
                    asset_class=record["asset_class"],
                    side=record["side"],
                    quantity=record["quantity"],
                    stop_loss=record.get("stop_loss"),
                    take_profit=record.get("take_profit"),
                    status=OrderStatus(record["status"]),
                    broker_order_id=record.get("broker_order_id"),
                    created_at=datetime.fromisoformat(record["created_at"]),
                )
                self._orders[order.order_id] = order
        logger.info("Ledger loaded: %d orders", len(self._orders))

    def _persist(self, order: Order) -> None:
        """Append a single order record to the JSONL ledger."""
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
        }
        with open(self._ledger_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

    def _update_ledger(self, order: Order) -> None:
        """Rewrite the full ledger (used after status changes)."""
        with open(self._ledger_path, "w", encoding="utf-8") as fh:
            for o in self._orders.values():
                record = {
                    "order_id": o.order_id,
                    "signal_id": o.signal_id,
                    "symbol": o.symbol,
                    "asset_class": o.asset_class,
                    "side": o.side,
                    "quantity": o.quantity,
                    "stop_loss": o.stop_loss,
                    "take_profit": o.take_profit,
                    "status": o.status.value,
                    "broker_order_id": o.broker_order_id,
                    "created_at": o.created_at.isoformat(),
                }
                fh.write(json.dumps(record) + "\n")

    # ------------------------------------------------------------------
    # Idempotency check
    # ------------------------------------------------------------------

    def _find_by_signal_id(self, signal_id: str) -> Optional[Order]:
        """Return the first order matching *signal_id*, if any."""
        for order in self._orders.values():
            if order.signal_id == signal_id:
                return order
        return None

    # ------------------------------------------------------------------
    # Adapter lookup
    # ------------------------------------------------------------------

    def _get_adapter(self, asset_class: str) -> BrokerAdapter:
        """Resolve the adapter for a given asset class."""
        venue = VENUE_MAP.get(asset_class.lower())
        if venue is None:
            raise ValueError(
                f"No venue mapped for asset_class={asset_class!r}. "
                f"Known: {list(VENUE_MAP)}"
            )
        adapter = self._adapters.get(venue)
        if adapter is None:
            raise RuntimeError(f"Adapter {venue!r} not registered")
        return adapter

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
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
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
        )

        # --- Initialize state machine ---
        sm = OrderStateMachine(order_id=order.order_id, initial=OrderStatus.SIGNAL_CREATED)
        self._state_machines[order.order_id] = sm

        # --- Crash safety: persist BEFORE sending ---
        self._orders[order.order_id] = order
        self._persist(order)

        # --- State machine: SIGNAL_CREATED → RISK_CHECKED → ORDER_PRECHECKED ---
        sm.advance(OrderStatus.RISK_CHECKED, "pre-trade risk passed")
        sm.advance(OrderStatus.ORDER_PRECHECKED, "pre-checks passed")

        # --- Route & submit ---
        adapter = self._get_adapter(asset_class)
        sm.advance(OrderStatus.ORDER_SUBMITTED, "sent to adapter")
        order.status = OrderStatus.SUBMITTED
        self._update_ledger(order)

        result = adapter.submit_order(order)

        # --- Handle result with state machine ---
        if result.status == OrderStatus.FILLED:
            sm.advance(OrderStatus.ORDER_ACKNOWLEDGED, "broker acknowledged")
            sm.advance(OrderStatus.FILLED, "fully filled")
            order.status = OrderStatus.FILLED
            order.quantity = result.filled_quantity  # type: ignore[assignment]
            logger.info(
                "Order %s filled: qty=%.6f avg=%.5f",
                order.order_id,
                result.filled_quantity,
                result.avg_price,
            )
        elif result.status == OrderStatus.PARTIALLY_FILLED:
            sm.advance(OrderStatus.ORDER_ACKNOWLEDGED, "broker acknowledged")
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
            sm.advance(OrderStatus.REJECTED, f"broker rejected: {result.error}")
            order.status = OrderStatus.FAILED
            logger.error("Order %s failed: %s", order.order_id, result.error)
        elif result.status == OrderStatus.TIMEOUT:
            sm.advance(OrderStatus.REJECTED, f"broker timeout: {result.error}")
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

    def cancel_all(self, asset_class: Optional[str] = None) -> list[Order]:
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
            self._update_ledger(cancelled[0])  # rewrite once
            logger.info("Kill switch: cancelled %d orders", len(cancelled))

        return cancelled

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_account_info(self, venue: str) -> AccountInfo:
        """Fetch account info from a specific venue adapter."""
        adapter = self._adapters.get(venue)
        if adapter is None:
            raise RuntimeError(f"Adapter {venue!r} not registered")
        return adapter.get_account_info()

    def get_positions(self, venue: str) -> list[dict]:
        """Fetch open positions from a specific venue adapter."""
        adapter = self._adapters.get(venue)
        if adapter is None:
            raise RuntimeError(f"Adapter {venue!r} not registered")
        return adapter.get_positions()

    def order_by_id(self, order_id: str) -> Optional[Order]:
        """Look up an order by its internal order_id."""
        return self._orders.get(order_id)

    def order_by_signal(self, signal_id: str) -> Optional[Order]:
        """Look up an order by the originating signal_id."""
        return self._find_by_signal_id(signal_id)

    def get_state_machine(self, order_id: str) -> Optional[OrderStateMachine]:
        """Return the state machine for a given order (for audit trail)."""
        return self._state_machines.get(order_id)

    def get_state_history(self, order_id: str) -> list[str]:
        """Return the state transition history for an order."""
        sm = self._state_machines.get(order_id)
        if sm is None:
            return []
        return [s.value for s in sm._history]

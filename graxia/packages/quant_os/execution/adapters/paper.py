"""Paper broker adapter for the unified adapter hierarchy.

Simulates execution with configurable slippage, commission and fill delays.
This is the canonical paper-trading implementation for Quant OS; the legacy
``PaperBroker`` in ``execution/broker_adapter.py`` is deprecated.
"""

from __future__ import annotations

import logging
import random
import uuid
from datetime import UTC, datetime

from ...core.config import get_config
from .base import AccountInfo, BrokerAdapter, Order, OrderResult, OrderStatus

logger = logging.getLogger(__name__)


class PaperAdapter(BrokerAdapter):
    """In-memory paper broker implementing the unified adapter interface."""

    def __init__(self, initial_capital: float | None = None) -> None:
        super().__init__("PAPER")
        config = get_config()
        self._initial_capital = initial_capital if initial_capital is not None else float(config.paper_initial_capital)
        self._cash = self._initial_capital
        self._equity = self._initial_capital
        self._prices: dict[str, dict[str, float]] = {}
        self._orders: dict[str, dict] = {}
        self._positions: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Paper adapter connects immediately."""
        self._connected = True
        return True

    def disconnect(self) -> None:
        """Paper adapter disconnects immediately."""
        self._connected = False

    # ------------------------------------------------------------------
    # Price simulation helpers
    # ------------------------------------------------------------------

    def get_price(self, symbol: str) -> dict[str, float]:
        """Return a simulated bid/ask price for ``symbol``."""
        if symbol in self._prices:
            return self._prices[symbol]

        base_prices = {
            "EURUSD": 1.0850,
            "GBPUSD": 1.2650,
            "USDJPY": 149.50,
            "AUDUSD": 0.6550,
            "USDCAD": 1.3550,
            "USDCHF": 0.8850,
            "NZDUSD": 0.6050,
            "XAUUSD": 3300.00,
            "BTCUSDT": 65000.00,
            "ETHUSDT": 3500.00,
        }
        base = base_prices.get(symbol, 1.0000)
        pip = 0.01 if "JPY" in symbol else 0.0001
        spread = pip * 1.5
        noise = base * random.uniform(-0.0005, 0.0005)
        bid = base + noise
        ask = bid + spread
        return {"bid": round(bid, 5), "ask": round(ask, 5)}

    def set_price(self, symbol: str, bid: float, ask: float) -> None:
        """Override the price for a symbol (useful in tests)."""
        self._prices[symbol] = {"bid": bid, "ask": ask}

    # ------------------------------------------------------------------
    # BrokerAdapter implementation
    # ------------------------------------------------------------------

    def submit_order(self, order: Order) -> OrderResult:
        """Simulate a market order fill."""
        try:
            price_data = self.get_price(order.symbol)
            market_price = price_data["ask"] if order.side.upper() == "BUY" else price_data["bid"]

            config = get_config()
            slippage_pips = random.uniform(0, float(config.paper_slippage_pips))
            pip = 0.01 if "JPY" in order.symbol else 0.0001
            slippage = slippage_pips * pip
            fill_price = market_price + slippage if order.side.upper() == "BUY" else market_price - slippage

            lot_size = float(getattr(config, "units_per_lot", 100000.0))
            lots = order.quantity / lot_size
            fee = lots * float(config.paper_commission_per_lot)

            broker_id = f"PAPER_{uuid.uuid4().hex[:12]}"
            self._orders[broker_id] = {
                "order": order,
                "broker_id": broker_id,
                "status": OrderStatus.FILLED,
                "filled_quantity": order.quantity,
                "avg_price": fill_price,
                "fee": fee,
                "filled_at": datetime.now(UTC),
            }

            self._cash -= fee
            self._update_position(order, fill_price)
            self._refresh_equity()

            return OrderResult(
                status=OrderStatus.FILLED,
                broker_id=broker_id,
                filled_quantity=order.quantity,
                avg_price=fill_price,
                fee=fee,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("PaperAdapter submit_order failed: %s", exc)
            return OrderResult(status=OrderStatus.FAILED, error=str(exc))

    def _update_position(self, order: Order, fill_price: float) -> None:
        """Update or clear the internal position for ``order.symbol``."""
        existing = self._positions.get(order.symbol)
        side = order.side.upper()

        if existing:
            existing_side = existing["side"]
            is_close = (existing_side == "BUY" and side == "SELL") or (existing_side == "SELL" and side == "BUY")
            if is_close:
                if order.quantity >= existing["quantity"]:
                    del self._positions[order.symbol]
                else:
                    existing["quantity"] -= order.quantity
            else:
                total_qty = existing["quantity"] + order.quantity
                avg = (existing["avg_price"] * existing["quantity"] + fill_price * order.quantity) / total_qty
                existing["quantity"] = total_qty
                existing["avg_price"] = avg
        else:
            self._positions[order.symbol] = {
                "symbol": order.symbol,
                "side": side,
                "quantity": order.quantity,
                "avg_price": fill_price,
            }

    def _refresh_equity(self) -> None:
        """Recalculate equity from cash and open positions."""
        unrealized = 0.0
        for symbol, pos in self._positions.items():
            price_data = self.get_price(symbol)
            mark = price_data["bid"] if pos["side"] == "BUY" else price_data["ask"]
            multiplier = 10.0 if "JPY" in symbol else 1.0
            unrealized += (mark - pos["avg_price"]) * pos["quantity"] * multiplier
        self._equity = self._cash + unrealized

    def cancel_order(self, broker_order_id: str) -> OrderResult:
        """Cancel a simulated order."""
        order_data = self._orders.get(broker_order_id)
        if order_data is None:
            return OrderResult(
                status=OrderStatus.FAILED,
                error=f"Order {broker_order_id} not found",
            )
        if order_data["status"] == OrderStatus.FILLED:
            return OrderResult(
                status=OrderStatus.FAILED,
                error="Cannot cancel an already filled order",
            )
        order_data["status"] = OrderStatus.CANCELLED
        return OrderResult(status=OrderStatus.CANCELLED, broker_id=broker_order_id)

    def get_order_status(self, broker_order_id: str) -> OrderResult:
        """Return the stored status of a simulated order."""
        order_data = self._orders.get(broker_order_id)
        if order_data is None:
            return OrderResult(
                status=OrderStatus.FAILED,
                error=f"Order {broker_order_id} not found",
            )
        return OrderResult(
            status=order_data["status"],
            broker_id=broker_order_id,
            filled_quantity=order_data["filled_quantity"],
            avg_price=order_data["avg_price"],
            fee=order_data.get("fee", 0.0),
        )

    def get_positions(self) -> list[dict]:
        """Return all open simulated positions."""
        self._refresh_equity()
        return [
            {
                "symbol": pos["symbol"],
                "side": pos["side"],
                "quantity": pos["quantity"],
                "avg_price": pos["avg_price"],
            }
            for pos in self._positions.values()
        ]

    def get_account_info(self) -> AccountInfo:
        """Return the simulated account snapshot."""
        self._refresh_equity()
        return AccountInfo(
            equity=self._equity,
            cash=self._cash,
            margin_used=0.0,
            margin_available=self._cash,
        )

    def close_position(self, broker_position_id: str, volume: float, symbol: str = "") -> OrderResult:
        """Close an open simulated position."""
        # broker_position_id is the symbol for PaperAdapter
        sym = symbol or broker_position_id
        existing = self._positions.get(sym)
        if existing is None:
            return OrderResult(
                status=OrderStatus.FAILED,
                error=f"No position for {sym}",
            )
        close_side = "SELL" if existing["side"] == "BUY" else "BUY"
        close_qty = min(volume, existing["quantity"])
        order = Order(
            order_id=f"CLOSE_{uuid.uuid4().hex[:8]}",
            signal_id="",
            symbol=sym,
            asset_class="",
            side=close_side,
            quantity=close_qty,
        )
        return self.submit_order(order)

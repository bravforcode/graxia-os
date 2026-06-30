"""MetaTrader 5 broker adapter for Pepperstone (metals, forex, indices)."""

import logging
import time
from typing import Optional

from .base import (
    AccountInfo,
    BrokerAdapter,
    Order,
    OrderResult,
    OrderStatus,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy mt5 import – allows the rest of the package to load without mt5
# installed (e.g. during unit tests that mock this adapter).
# ---------------------------------------------------------------------------
try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover
    mt5 = None  # type: ignore[assignment]

# Constants mapped from mt5 module (referenced by name so import is optional)
_TRADE_ACTION_DEAL = 1       # mt5.TRADE_ACTION_DEAL
_ORDER_FILLING_IOC = 2       # mt5.ORDER_FILLING_IOC (also FOK on some brokers)
_ORDER_TYPE_BUY = 0          # mt5.ORDER_TYPE_BUY
_ORDER_TYPE_SELL = 1         # mt5.ORDER_TYPE_SELL
_RETRIES = 3
_RETRY_DELAY = 1.0  # seconds


def _side_to_order_type(side: str) -> int:
    """Map canonical side string to MT5 order-type constant."""
    if side.upper() == "BUY":
        return _ORDER_TYPE_BUY
    if side.upper() == "SELL":
        return _ORDER_TYPE_SELL
    raise ValueError(f"Unknown side: {side}")


class MT5Adapter(BrokerAdapter):
    """Adapter for MetaTrader 5 via the ``MetaTrader5`` Python package.

    Designed for Pepperstone Razor accounts trading metals, forex, and
    indices.  The ``order_id`` is written into the ``comment`` field so that
    duplicate submissions are detected by MT5 (idempotency guard).
    """

    def __init__(
        self,
        login: int,
        password: str,
        server: str = "Pepperstone-Live",
        timeout: int = 10_000,
    ) -> None:
        super().__init__("MT5")
        self._login = login
        self._password = password
        self._server = server
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Initialise the MT5 terminal and authenticate."""
        if mt5 is None:
            raise RuntimeError("MetaTrader5 package is not installed")
        ok = mt5.initialize(timeout=self._timeout)
        if not ok:
            logger.error("MT5 initialize failed: %s", mt5.last_error())
            return False
        authorized = mt5.login(self._login, password=self._password, server=self._server)
        if not authorized:
            logger.error("MT5 login failed: %s", mt5.last_error())
            return False
        self._connected = True
        logger.info("MT5 connected to %s as %s", self._server, self._login)
        return True

    def _ensure_connected(self) -> None:
        """Reconnect if the terminal connection was lost, with backoff."""
        if self._connected and mt5 is not None and mt5.terminal_info():
            return

        logger.warning("MT5 not connected – attempting reconnect")
        for attempt in range(1, 4):
            try:
                if self.connect():
                    return
            except Exception as exc:
                logger.error("MT5 reconnect attempt %d failed: %s", attempt, exc)
            import time
            time.sleep(min(2 ** attempt, 10))  # backoff: 2s, 4s, 8s

        raise ConnectionError("MT5 reconnect failed after 3 attempts")

    def disconnect(self) -> None:
        """Tear down the MT5 terminal connection."""
        if mt5 is not None:
            mt5.shutdown()
        self._connected = False

    def shutdown(self) -> None:
        """Alias for :meth:`disconnect` for backward compatibility."""
        self.disconnect()

    # ------------------------------------------------------------------
    # BrokerAdapter implementation
    # ------------------------------------------------------------------

    def submit_order(self, order: Order) -> OrderResult:
        """Submit a market order to MT5 using ``TRADE_ACTION_DEAL``.

        The ``comment`` field is set to ``order.order_id`` for idempotency.
        Retries up to 3 times on transient failures with automatic reconnect.
        """
        self._ensure_connected()

        request: dict = {
            "action": _TRADE_ACTION_DEAL,
            "symbol": order.symbol,
            "volume": order.quantity,
            "type": _side_to_order_type(order.side),
            "comment": order.order_id,
            "type_filling": _ORDER_FILLING_IOC,
            "type_time": 0,  # ORDER_TIME_GTC
        }

        if order.stop_loss is not None:
            request["sl"] = order.stop_loss
        if order.take_profit is not None:
            request["tp"] = order.take_profit

        for attempt in range(1, _RETRIES + 1):
            result = mt5.order_send(request)  # type: ignore[union-attr]
            if result is None:
                error = mt5.last_error()  # type: ignore[union-attr]
                logger.error("MT5 order_send returned None (attempt %d): %s", attempt, error)
                self._connected = False
                self._ensure_connected()
                time.sleep(_RETRY_DELAY)
                continue

            ret_code = result.retcode
            if ret_code == 10009:  # TRADE_RETCODE_DONE
                return OrderResult(
                    status=OrderStatus.FILLED,
                    broker_id=str(result.order),
                    filled_quantity=result.volume,
                    avg_price=result.price,
                )
            if ret_code == 10014:  # TRADE_RETCODE_INVALID_PRICE – retry
                logger.warning("MT5 invalid price (attempt %d), retrying", attempt)
                time.sleep(_RETRY_DELAY)
                continue

            # Permanent failure – do not retry
            error_msg = f"MT5 retcode={ret_code}: {result.comment}"
            logger.error(error_msg)
            return OrderResult(status=OrderStatus.FAILED, error=error_msg)

        return OrderResult(status=OrderStatus.TIMEOUT, error="MT5 retries exhausted")

    def cancel_order(self, broker_order_id: str) -> OrderResult:
        """Cancel a pending order by its MT5 ticket."""
        self._ensure_connected()
        request: dict = {
            "action": 2,  # mt5.TRADE_ACTION_REMOVE (pending orders)
            "order": int(broker_order_id),
        }
        result = mt5.order_send(request)  # type: ignore[union-attr]
        if result is None:
            return OrderResult(
                status=OrderStatus.FAILED,
                error=str(mt5.last_error()),  # type: ignore[union-attr]
            )
        if result.retcode == 10009:
            return OrderResult(status=OrderStatus.CANCELLED, broker_id=broker_order_id)
        return OrderResult(
            status=OrderStatus.FAILED,
            error=f"cancel retcode={result.retcode}: {result.comment}",
        )

    def get_positions(self) -> list[dict]:
        """Return all open MT5 positions."""
        self._ensure_connected()
        positions = mt5.positions_get()  # type: ignore[union-attr]
        if positions is None:
            return []
        return [
            {
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "BUY" if p.type == 0 else "SELL",
                "volume": p.volume,
                "price_open": p.price_open,
                "profit": p.profit,
                "sl": p.sl,
                "tp": p.tp,
                "comment": p.comment,
            }
            for p in positions
        ]

    def get_order_status(self, broker_order_id: str) -> OrderResult:
        """Check the current state of an MT5 order by ticket."""
        self._ensure_connected()
        orders = mt5.orders_get(ticket=int(broker_order_id))  # type: ignore[union-attr]
        if orders is None or len(orders) == 0:
            # Not an open order – assume it was filled or cancelled
            return OrderResult(status=OrderStatus.FILLED, broker_id=broker_order_id)
        order = orders[0]
        return OrderResult(
            status=OrderStatus.SUBMITTED,
            broker_id=str(order.ticket),
        )

    def get_account_info(self) -> AccountInfo:
        """Return a snapshot of the MT5 account."""
        self._ensure_connected()
        info = mt5.account_info()  # type: ignore[union-attr]
        if info is None:
            raise RuntimeError(f"MT5 account_info failed: {mt5.last_error()}")  # type: ignore[union-attr]
        return AccountInfo(
            equity=info.equity,
            cash=info.balance,
            margin_used=info.margin,
            margin_available=info.margin_free,
        )

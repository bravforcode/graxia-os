"""MetaTrader 5 broker adapter for Pepperstone (metals, forex, indices)."""

import hashlib
import logging
import time

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
_TRADE_ACTION_DEAL = 1  # mt5.TRADE_ACTION_DEAL
_TRADE_ACTION_SLTP = 5  # mt5.TRADE_ACTION_SLTP
_ORDER_FILLING_FOK = 0  # mt5.ORDER_FILLING_FOK (Fill or Kill)
_ORDER_FILLING_IOC = 1  # mt5.ORDER_FILLING_IOC (Immediate or Cancel)
_ORDER_FILLING_RETURN = 2  # mt5.ORDER_FILLING_RETURN (Good Till Cancelled)
_ORDER_TYPE_BUY = 0  # mt5.ORDER_TYPE_BUY
_ORDER_TYPE_SELL = 1  # mt5.ORDER_TYPE_SELL
_RETRIES = 3
_RETRY_DELAY = 1.0  # seconds


def _side_to_order_type(side: str) -> int:
    """Map canonical side string to MT5 order-type constant."""
    if side.upper() == "BUY":
        return _ORDER_TYPE_BUY
    if side.upper() == "SELL":
        return _ORDER_TYPE_SELL
    raise ValueError(f"Unknown side: {side}")


def _get_filling_mode(symbol: str) -> int:
    """Detect the best filling mode for a symbol from MT5 symbol info.

    Pepperstone supports FOK (0) and RETURN (2) for most instruments.
    IOC (1) is NOT supported for indices/CFDs. Falls back to RETURN (2)
    if symbol info is unavailable.
    """
    if mt5 is None:
        return _ORDER_FILLING_RETURN
    info = mt5.symbol_info(symbol)
    if info is None:
        logger.warning("symbol_info returned None for %s — using RETURN filling", symbol)
        return _ORDER_FILLING_RETURN
    # filling_mode is a bitmask: bit 0 = FOK, bit 1 = IOC, bit 2 = RETURN
    filling = info.filling_mode
    if filling & 4:  # bit 2 set → RETURN supported
        return _ORDER_FILLING_RETURN
    if filling & 1:  # bit 0 set → FOK supported
        return _ORDER_FILLING_FOK
    if filling & 2:  # bit 1 set → IOC supported
        return _ORDER_FILLING_IOC
    # Default to RETURN (most widely supported on Pepperstone)
    return _ORDER_FILLING_RETURN


def _ensure_symbol_visible(symbol: str) -> bool:
    """Ensure a symbol is in MT5 Market Watch so it receives live ticks.

    Returns True if the symbol is available for trading.
    """
    if mt5 is None:
        return False
    info = mt5.symbol_info(symbol)
    if info is None:
        logger.error("Symbol %s not found in MT5 — check symbol name", symbol)
        return False
    if not info.visible:
        logger.info("Symbol %s not in Market Watch — adding it", symbol)
        selected = mt5.symbol_select(symbol, True)
        if not selected:
            logger.error("Failed to add %s to Market Watch", symbol)
            return False
        # Brief pause for the first tick to arrive
        time.sleep(0.3)
    return True


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
        path: str = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe",
    ) -> None:
        super().__init__("MT5")
        self._login = login
        self._password = password
        self._server = server
        self._timeout = timeout
        self._path = path

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Initialise the MT5 terminal and authenticate."""
        if mt5 is None:
            raise RuntimeError("MetaTrader5 package is not installed")
        ok = mt5.initialize(path=self._path, timeout=self._timeout)
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

            time.sleep(min(2**attempt, 10))  # backoff: 2s, 4s, 8s

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

        Filling mode is auto-detected per symbol (FOK vs RETURN) because
        Pepperstone indices do NOT support IOC — only FOK and RETURN.
        """
        self._ensure_connected()

        # Ensure symbol is in Market Watch (required for live ticks)
        if not _ensure_symbol_visible(order.symbol):
            return OrderResult(
                status=OrderStatus.FAILED,
                error=f"Symbol {order.symbol} not found or not visible in MT5",
            )

        # Cast quantity to float (defensive: may be str or Decimal)
        try:
            qty_float = float(order.quantity)
        except (TypeError, ValueError) as exc:
            return OrderResult(
                status=OrderStatus.FAILED,
                error=f"Invalid quantity {order.quantity!r}: {exc}",
            )

        # Auto-detect filling mode (FOK vs RETURN — Pepperstone indices need RETURN)
        filling_mode = _get_filling_mode(order.symbol)

        request: dict = {
            "action": _TRADE_ACTION_DEAL,
            "symbol": order.symbol,
            "volume": qty_float,
            "type": _side_to_order_type(order.side),
            "comment": hashlib.md5(order.order_id.encode()).hexdigest()[:8],  # Short alphanumeric comment for tracking
            "type_filling": filling_mode,
            "type_time": 0,  # ORDER_TIME_GTC
        }

        if order.stop_loss is not None:
            request["sl"] = order.stop_loss
        if order.take_profit is not None:
            request["tp"] = order.take_profit

        logger.info(
            "MT5 submit_order: symbol=%s side=%s qty=%.2f filling=%d",
            order.symbol,
            order.side,
            qty_float,
            filling_mode,
        )

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
                # Sanity check fill result data
                if result.price <= 0:
                    logger.error("MT5 fill returned invalid price=%.5f — treating as FAILED", result.price)
                    return OrderResult(
                        status=OrderStatus.FAILED,
                        error=f"Invalid fill price: {result.price}",
                    )
                if result.volume <= 0:
                    logger.error("MT5 fill returned invalid volume=%.2f — treating as FAILED", result.volume)
                    return OrderResult(
                        status=OrderStatus.FAILED,
                        error=f"Invalid fill volume: {result.volume}",
                    )
                # Detect partial fills: filled_volume < requested
                if result.volume < qty_float:
                    logger.warning(
                        "MT5 partial fill: ticket=%s filled=%.2f requested=%.2f",
                        result.order,
                        result.volume,
                        order.quantity,
                    )
                    return OrderResult(
                        status=OrderStatus.PARTIALLY_FILLED,
                        broker_id=str(result.order),
                        filled_quantity=result.volume,
                        avg_price=result.price,
                    )
                logger.info(
                    "MT5 order filled: ticket=%s price=%.5f vol=%.2f",
                    result.order,
                    result.price,
                    result.volume,
                )
                return OrderResult(
                    status=OrderStatus.FILLED,
                    broker_id=str(result.order),
                    filled_quantity=result.volume,
                    avg_price=result.price,
                )
            if ret_code == 10014:  # TRADE_RETCODE_INVALID_PRICE – retry
                logger.warning(
                    "MT5 invalid price (attempt %d): symbol=%s retcode=%d comment=%s — retrying",
                    attempt,
                    order.symbol,
                    ret_code,
                    result.comment,
                )
                time.sleep(_RETRY_DELAY)
                continue

            # Permanent failure – do not retry
            error_msg = f"MT5 retcode={ret_code}: {result.comment} (symbol={order.symbol}, filling={filling_mode})"
            logger.error(error_msg)
            return OrderResult(status=OrderStatus.FAILED, error=error_msg)

        return OrderResult(status=OrderStatus.TIMEOUT, error="MT5 retries exhausted")

    def cancel_order(self, broker_order_id: str) -> OrderResult:
        """Cancel a pending order by its MT5 ticket. Retries on transient failures."""
        self._ensure_connected()
        request: dict = {
            "action": 2,  # mt5.TRADE_ACTION_REMOVE (pending orders)
            "order": int(broker_order_id),
        }

        for attempt in range(1, _RETRIES + 1):
            result = mt5.order_send(request)  # type: ignore[union-attr]
            if result is None:
                error = mt5.last_error()  # type: ignore[union-attr]
                logger.error("MT5 cancel_order returned None (attempt %d): %s", attempt, error)
                self._connected = False
                self._ensure_connected()
                time.sleep(_RETRY_DELAY)
                continue
            if result.retcode == 10009:
                return OrderResult(status=OrderStatus.CANCELLED, broker_id=broker_order_id)
            if result.retcode == 10014:  # invalid price — retry
                time.sleep(_RETRY_DELAY)
                continue
            return OrderResult(
                status=OrderStatus.FAILED,
                error=f"cancel retcode={result.retcode}: {result.comment}",
            )

        return OrderResult(status=OrderStatus.TIMEOUT, error="cancel_order retries exhausted")

    def get_positions(self) -> list[dict]:
        """Return all open MT5 positions."""
        self._ensure_connected()
        positions = mt5.positions_get()  # type: ignore[union-attr]
        if positions is None:
            return []
        result = []
        for p in positions:
            if p is None:
                logger.warning("MT5 positions_get returned None item — skipping")
                continue
            result.append(
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
            )
        return result

    def get_order_status(self, broker_order_id: str) -> OrderResult:
        """Check the current state of an MT5 order by ticket.

        Returns UNKNOWN when the order is not found in MT5's open orders list.
        This avoids the previous bug of defaulting to FILLED, which could cause
        the strategy to believe a rejected/cancelled order was executed.
        """
        self._ensure_connected()
        orders = mt5.orders_get(ticket=int(broker_order_id))  # type: ignore[union-attr]
        if orders is None or len(orders) == 0:
            # Not an open order — could be filled, cancelled, or expired.
            # Return UNKNOWN so the caller checks position history.
            logger.warning(
                "MT5 order %s not found in open orders — returning UNKNOWN (check fills)",
                broker_order_id,
            )
            return OrderResult(
                status=OrderStatus.UNKNOWN,
                broker_id=broker_order_id,
                error="Order not found in MT5 open orders",
            )
        order = orders[0]
        return OrderResult(
            status=OrderStatus.SUBMITTED,
            broker_id=str(order.ticket),
        )

    def close_position(self, broker_position_id: str, volume: float, symbol: str = "") -> OrderResult:
        """Close an open position by its MT5 ticket.

        Sends a ``TRADE_ACTION_DEAL`` in the opposite direction of the
        existing position to flatten it.
        """
        self._ensure_connected()
        # Determine position type to send opposite order
        positions = mt5.positions_get(ticket=int(broker_position_id))  # type: ignore[union-attr]
        if positions is None or len(positions) == 0:
            return OrderResult(
                status=OrderStatus.FAILED,
                error=f"Position {broker_position_id} not found",
            )
        pos = positions[0]
        close_type = _ORDER_TYPE_SELL if pos.type == _ORDER_TYPE_BUY else _ORDER_TYPE_BUY
        close_symbol = symbol or pos.symbol

        # Auto-detect filling mode for the symbol
        filling_mode = _get_filling_mode(close_symbol)

        request: dict = {
            "action": _TRADE_ACTION_DEAL,
            "symbol": close_symbol,
            "volume": volume,
            "type": close_type,
            "position": int(broker_position_id),
            "type_filling": filling_mode,
            "type_time": 0,
        }

        for attempt in range(1, _RETRIES + 1):
            result = mt5.order_send(request)  # type: ignore[union-attr]
            if result is None:
                error = mt5.last_error()  # type: ignore[union-attr]
                logger.error("MT5 close_position returned None (attempt %d): %s", attempt, error)
                self._connected = False
                self._ensure_connected()
                time.sleep(_RETRY_DELAY)
                continue
            if result.retcode == 10009:
                return OrderResult(
                    status=OrderStatus.FILLED,
                    broker_id=str(result.order),
                    filled_quantity=result.volume,
                    avg_price=result.price,
                )
            if result.retcode == 10014:
                logger.warning("MT5 close_position invalid price (attempt %d), retrying", attempt)
                time.sleep(_RETRY_DELAY)
                continue
            error_msg = f"MT5 close retcode={result.retcode}: {result.comment}"
            logger.error(error_msg)
            return OrderResult(status=OrderStatus.FAILED, error=error_msg)

        return OrderResult(status=OrderStatus.TIMEOUT, error="MT5 close_position retries exhausted")

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

    # ------------------------------------------------------------------
    # Stop-loss management
    # ------------------------------------------------------------------

    def set_stop_loss(
        self,
        position_ticket: int,
        symbol: str,
        stop_loss_price: float,
        take_profit: float | None = None,
    ) -> bool:
        """Set or modify the stop-loss (and optionally TP) on an open position.

        Uses ``TRADE_ACTION_SLTP``.  Retries up to 3 times on
        ``TRADE_RETCODE_INVALID_PRICE`` (10014) with auto-reconnect.
        Returns ``True`` on success, ``False`` on permanent failure or
        exhausted retries.
        """
        self._ensure_connected()

        request: dict = {
            "action": _TRADE_ACTION_SLTP,
            "position": position_ticket,
            "symbol": symbol,
            "sl": stop_loss_price,
        }
        if take_profit is not None:
            request["tp"] = take_profit

        for attempt in range(1, _RETRIES + 1):
            result = mt5.order_send(request)  # type: ignore[union-attr]
            if result is None:
                error = mt5.last_error()  # type: ignore[union-attr]
                logger.error("MT5 set_stop_loss returned None (attempt %d): %s", attempt, error)
                self._connected = False
                self._ensure_connected()
                time.sleep(_RETRY_DELAY)
                continue

            ret_code = result.retcode
            if ret_code == 10009:  # TRADE_RETCODE_DONE
                return True
            if ret_code == 10014:  # TRADE_RETCODE_INVALID_PRICE – retry
                logger.warning("MT5 set_stop_loss invalid price (attempt %d), retrying", attempt)
                time.sleep(_RETRY_DELAY)
                continue

            # Permanent failure – do not retry
            logger.error("MT5 set_stop_loss failed: retcode=%d %s", ret_code, result.comment)
            return False

        return False  # retries exhausted

    def update_trailing_stop(
        self,
        position_ticket: int,
        symbol: str,
        side: str,
        entry_price: float,
        current_price: float,
        atr_value: float,
        trail_multiplier: float = 2.0,
    ) -> bool:
        """Update trailing stop-loss on an open position.

        BUY:  new SL = current_price - (ATR * multiplier)  — only moves UP.
        SELL: new SL = current_price + (ATR * multiplier)  — only moves DOWN.

        Returns ``True`` if the SL was updated, ``False`` if no move was
        needed, ATR is negative, side is unknown, or the position was not
        found.
        """
        if atr_value <= 0:
            return False

        side_upper = side.upper()
        if side_upper not in ("BUY", "SELL"):
            return False

        self._ensure_connected()

        # Look up the current position
        positions = mt5.positions_get(ticket=position_ticket)  # type: ignore[union-attr]
        if positions is None or len(positions) == 0:
            return False

        pos = positions[0]
        current_sl = pos.sl

        if side_upper == "BUY":
            new_sl = round(current_price - (atr_value * trail_multiplier), 5)
            if new_sl <= current_sl:
                return False  # would move SL down — never trail backward
        else:  # SELL
            new_sl = round(current_price + (atr_value * trail_multiplier), 5)
            if new_sl >= current_sl and current_sl > 0:
                return False  # would move SL up — never trail backward

        request: dict = {
            "action": _TRADE_ACTION_SLTP,
            "position": position_ticket,
            "symbol": symbol,
            "sl": new_sl,
        }

        result = mt5.order_send(request)  # type: ignore[union-attr]
        if result is None:
            error = mt5.last_error()  # type: ignore[union-attr]
            logger.error("MT5 update_trailing_stop returned None: %s", error)
            return False
        if result.retcode == 10009:
            return True

        logger.error(
            "MT5 update_trailing_stop failed: retcode=%d %s",
            result.retcode,
            result.comment,
        )
        return False

    def set_fixed_atr_stop(
        self,
        position_ticket: int,
        symbol: str,
        side: str,
        entry_price: float,
        atr_value: float,
        atr_multiplier: float,
    ) -> bool:
        """Set a fixed ATR-based stop-loss on an open position.

        BUY:  SL = entry_price - (ATR * multiplier)
        SELL: SL = entry_price + (ATR * multiplier)

        Returns ``False`` if ATR is negative.
        """
        if atr_value <= 0:
            return False

        side_upper = side.upper()
        if side_upper == "BUY":
            sl_price = round(entry_price - (atr_value * atr_multiplier), 5)
        elif side_upper == "SELL":
            sl_price = round(entry_price + (atr_value * atr_multiplier), 5)
        else:
            return False

        return self.set_stop_loss(
            position_ticket=position_ticket,
            symbol=symbol,
            stop_loss_price=sl_price,
        )

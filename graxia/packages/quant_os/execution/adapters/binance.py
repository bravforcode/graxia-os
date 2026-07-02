"""Binance broker adapter via ccxt (crypto spot & futures)."""

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

try:
    import ccxt
except ImportError:  # pragma: no cover
    ccxt = None  # type: ignore[assignment]

_RATE_LIMIT_PAUSE = 0.5  # seconds between calls when rate-limited
_MAX_RETRIES = 3


class BinanceAdapter(BrokerAdapter):
    """Adapter for Binance via the ``ccxt`` unified API.

    Supports both spot and USDT-margined perpetual futures.  The
    ``newClientOrderId`` parameter is set to the canonical ``order_id``
    so that duplicate submissions are rejected by the exchange (idempotency).
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = False,
        default_type: str = "future",
    ) -> None:
        if ccxt is None:
            raise RuntimeError("ccxt package is not installed")

        super().__init__("BINANCE")
        self._api_key = api_key
        self._api_secret = api_secret
        self._testnet = testnet
        self._default_type = default_type
        self._exchange = ccxt.binance(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
                "options": {
                    "defaultType": default_type,
                    "adjustForTimeDifference": True,
                },
            }
        )
        if testnet:
            self._exchange.set_sandbox_mode(True)
        self._last_call: float = 0.0
        self._order_symbols: dict[str, str] = {}  # broker_order_id -> symbol

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Load markets and confirm the exchange is reachable."""
        try:
            self._throttle()
            self._exchange.load_markets()
            self._connected = True
            return True
        except ccxt.AuthenticationError as exc:
            raise RuntimeError(f"Binance authentication failed: {exc}") from exc
        except ccxt.NetworkError as exc:
            raise ConnectionError(f"Binance connection failed: {exc}") from exc
        except ccxt.ExchangeError as exc:
            raise RuntimeError(f"Binance connect failed: {exc}") from exc

    def disconnect(self) -> None:
        """Release the exchange reference."""
        self._exchange = None  # type: ignore[assignment]
        self._connected = False

    # ------------------------------------------------------------------
    # Rate-limit guard (applied on top of ccxt built-in limiter)
    # ------------------------------------------------------------------

    def _throttle(self) -> None:
        """Enforce a minimum gap between API calls."""
        now = time.monotonic()
        elapsed = now - self._last_call
        if elapsed < _RATE_LIMIT_PAUSE:
            time.sleep(_RATE_LIMIT_PAUSE - elapsed)
        self._last_call = time.monotonic()

    # ------------------------------------------------------------------
    # Status mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _map_ccxt_status(status: str) -> OrderStatus:
        """Map a ccxt unified order status string to our OrderStatus enum."""
        return {
            "open": OrderStatus.SUBMITTED,
            "closed": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELLED,
            "expired": OrderStatus.CANCELLED,
        }.get(status, OrderStatus.FAILED)

    # ------------------------------------------------------------------
    # BrokerAdapter implementation
    # ------------------------------------------------------------------

    def submit_order(self, order: Order) -> OrderResult:
        """Place a market order on Binance with ``newClientOrderId``.

        Retries up to 3 times on transient rate-limit / network errors.
        """
        side = "buy" if order.side.upper() == "BUY" else "sell"
        params: dict = {"newClientOrderId": order.order_id}

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                self._throttle()
                result = self._exchange.create_order(
                    symbol=order.symbol,
                    type="market",
                    side=side,
                    amount=order.quantity,
                    params=params,
                )
                broker_id = str(result.get("id", ""))
                self._order_symbols[broker_id] = order.symbol
                return OrderResult(
                    status=OrderStatus.FILLED,
                    broker_id=broker_id,
                    filled_quantity=float(result.get("filled", order.quantity)),
                    avg_price=float(result.get("average", 0.0) or 0.0),
                )
            except ccxt.InvalidOrder as exc:
                error_msg = f"Binance invalid order: {exc}"
                logger.error(error_msg)
                return OrderResult(status=OrderStatus.FAILED, error=error_msg)
            except ccxt.InsufficientFunds as exc:
                error_msg = f"Binance insufficient funds: {exc}"
                logger.error(error_msg)
                return OrderResult(status=OrderStatus.FAILED, error=error_msg)
            except ccxt.RateLimitExceeded:
                logger.warning("Binance rate limit (attempt %d), backing off", attempt)
                time.sleep(_RATE_LIMIT_PAUSE * attempt * 2)
                continue
            except ccxt.NetworkError as exc:
                logger.warning("Binance network error (attempt %d): %s", attempt, exc)
                time.sleep(_RATE_LIMIT_PAUSE * attempt)
                continue
            except ccxt.ExchangeError as exc:
                error_msg = f"Binance exchange error: {exc}"
                logger.error(error_msg)
                return OrderResult(status=OrderStatus.FAILED, error=error_msg)

        return OrderResult(status=OrderStatus.TIMEOUT, error="Binance retries exhausted")

    def cancel_order(self, broker_order_id: str) -> OrderResult:
        """Cancel an open order on Binance.

        Uses the internally tracked symbol mapping.  Returns FAILED if
        the symbol is unknown (order not submitted through this adapter).
        """
        symbol = self._order_symbols.get(broker_order_id)
        if symbol is None:
            return OrderResult(
                status=OrderStatus.FAILED,
                error=f"Unknown symbol for order {broker_order_id}",
            )
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                self._throttle()
                self._exchange.cancel_order(broker_order_id, symbol)
                return OrderResult(status=OrderStatus.CANCELLED, broker_id=broker_order_id)
            except ccxt.RateLimitExceeded:
                logger.warning("Binance cancel rate limit (attempt %d), backing off", attempt)
                time.sleep(_RATE_LIMIT_PAUSE * attempt * 2)
                continue
            except ccxt.NetworkError as exc:
                logger.warning("Binance cancel network error (attempt %d): %s", attempt, exc)
                time.sleep(_RATE_LIMIT_PAUSE * attempt)
                continue
            except ccxt.ExchangeError as exc:
                return OrderResult(status=OrderStatus.FAILED, error=str(exc))

        return OrderResult(status=OrderStatus.TIMEOUT, error="Binance cancel retries exhausted")

    def get_positions(self) -> list[dict]:
        """Return all open futures positions."""
        try:
            self._throttle()
            positions = self._exchange.fetch_positions()
            return [
                {
                    "symbol": p["symbol"],
                    "side": p["side"],
                    "quantity": abs(float(p.get("contracts", 0))),
                    "entry_price": float(p.get("entryPrice", 0) or 0),
                    "unrealized_pnl": float(p.get("unrealizedPnl", 0) or 0),
                    "leverage": p.get("leverage"),
                }
                for p in positions
                if float(p.get("contracts", 0)) != 0
            ]
        except ccxt.ExchangeError as exc:
            logger.error("Binance get_positions failed: %s", exc)
            return []

    def get_order_status(self, broker_order_id: str) -> OrderResult:
        """Poll order status from Binance.

        Uses the internally tracked symbol mapping.  Returns FAILED if
        the symbol is unknown (order not submitted through this adapter).
        """
        symbol = self._order_symbols.get(broker_order_id)
        if symbol is None:
            return OrderResult(
                status=OrderStatus.FAILED,
                error=f"Unknown symbol for order {broker_order_id}",
            )
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                self._throttle()
                result = self._exchange.fetch_order(broker_order_id, symbol)
                status = self._map_ccxt_status(result.get("status", ""))
                return OrderResult(
                    status=status,
                    broker_id=broker_order_id,
                    filled_quantity=float(result.get("filled", 0) or 0),
                    avg_price=float(result.get("average", 0) or 0),
                )
            except ccxt.RateLimitExceeded:
                logger.warning("Binance fetch status rate limit (attempt %d), backing off", attempt)
                time.sleep(_RATE_LIMIT_PAUSE * attempt * 2)
                continue
            except ccxt.NetworkError as exc:
                logger.warning("Binance fetch status network error (attempt %d): %s", attempt, exc)
                time.sleep(_RATE_LIMIT_PAUSE * attempt)
                continue
            except ccxt.ExchangeError as exc:
                return OrderResult(status=OrderStatus.FAILED, error=str(exc))

        return OrderResult(status=OrderStatus.TIMEOUT, error="Binance fetch status retries exhausted")

    def get_account_info(self) -> AccountInfo:
        """Return a snapshot of the Binance account balances."""
        try:
            self._throttle()
            balance = self._exchange.fetch_balance()
            total = float(balance.get("total", {}).get("USDT", 0) or 0)
            free = float(balance.get("free", {}).get("USDT", 0) or 0)
            used = float(balance.get("used", {}).get("USDT", 0) or 0)
            return AccountInfo(
                equity=total,
                cash=free,
                margin_used=used,
                margin_available=free,
            )
        except ccxt.ExchangeError as exc:
            raise RuntimeError(f"Binance account_info failed: {exc}") from exc

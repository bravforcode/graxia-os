"""
Myfxbook adapter for the unified broker-adapter hierarchy.

Myfxbook is a READ-ONLY analytics mirror of a trading account (it cannot
submit/cancel/close orders). This adapter implements the canonical
``BrokerAdapter`` interface so it can feed account state (equity, balance)
and open positions into the risk engine / orchestrator exactly like the MT5
and Binance adapters.

Trading operations are intentionally refused (raise ``BrokerError``) so the
system fails closed instead of silently attempting to trade through a
non-executing venue. Richer analytics (gain, drawdown, profit factor, history)
are exposed via the extra ``get_account_analytics`` / ``get_history`` /
``get_daily_gain`` methods.
"""

from __future__ import annotations

import logging

from ...broker.myfxbook_gateway import MyfxbookGateway
from ...core.exceptions import BrokerError
from .base import AccountInfo, BrokerAdapter, Order, OrderResult, OrderStatus

logger = logging.getLogger(__name__)


class MyfxbookAdapter(BrokerAdapter):
    """Read-only account-data adapter backed by the Myfxbook API."""

    def __init__(
        self,
        email: str | None = None,
        password: str | None = None,
        account_id: int | None = None,
        gateway: MyfxbookGateway | None = None,
    ) -> None:
        super().__init__("MYFXBOOK")
        self._gateway = gateway or MyfxbookGateway(email=email, password=password)
        # Restrict to a single account; if None the first linked account is used.
        self._account_id = account_id

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Authenticate against the Myfxbook API."""
        self._gateway.login()
        self._connected = True
        return True

    def disconnect(self) -> None:
        """Log out and drop the cached session."""
        try:
            self._gateway.logout()
        finally:
            self._connected = False

    # ------------------------------------------------------------------
    # Account selection helpers
    # ------------------------------------------------------------------

    def list_accounts(self) -> list[dict]:
        """Return all linked accounts (handy for choosing ``account_id``)."""
        return list(self._gateway.get_my_accounts())

    def _select_account(self) -> dict:
        accounts = self._gateway.get_my_accounts()
        if not accounts:
            raise BrokerError("Myfxbook: no linked accounts returned")
        if self._account_id is not None:
            for acct in accounts:
                if str(acct.get("id")) == str(self._account_id):
                    return dict(acct)
            raise BrokerError(f"Myfxbook: account id {self._account_id} not found")
        return dict(accounts[0])

    # ------------------------------------------------------------------
    # BrokerAdapter implementation (read-only)
    # ------------------------------------------------------------------

    def get_account_info(self) -> AccountInfo:
        """Map Myfxbook account analytics to the canonical ``AccountInfo``.

        Myfxbook does not expose margin used / free, so those are mapped
        conservatively (margin_used=0, margin_available=equity). This is
        honest given the source, not a fabricated value.
        """
        acct = self._select_account()
        equity = _to_float(acct.get("equity"))
        balance = _to_float(acct.get("balance"))
        return AccountInfo(
            equity=equity,
            cash=balance,
            margin_used=0.0,
            margin_available=equity,
        )

    def get_positions(self) -> list[dict]:
        """Return open trades as position dicts (read-only)."""
        acct = self._select_account()
        trades = self._gateway.get_open_trades(acct.get("id"))  # type: ignore[arg-type]
        positions = []
        for t in trades:
            sizing = t.get("sizing") if isinstance(t.get("sizing"), dict) else {}
            action = (t.get("action") or "").lower()
            side = "BUY" if "buy" in action else "SELL"
            positions.append(
                {
                    "symbol": t.get("symbol", ""),
                    "side": side,
                    "quantity": _to_float(sizing.get("value") if isinstance(sizing, dict) else 0.0),
                    "avg_price": _to_float(t.get("openPrice")),
                    "profit": _to_float(t.get("profit")),
                    "pips": _to_float(t.get("pips")),
                    "open_date": t.get("openDate", ""),
                }
            )
        return positions

    # ------------------------------------------------------------------
    # Richer analytics (beyond the canonical interface)
    # ------------------------------------------------------------------

    def get_account_analytics(self) -> dict:
        """Return the full account analytics dict (gain, drawdown, etc.)."""
        return self._select_account()

    def get_history(self, start: str | None = None, end: str | None = None) -> list[dict]:
        """Return trade history (Myfxbook caps this at the last 50)."""
        acct = self._select_account()
        return list(self._gateway.get_history(acct.get("id"), start=start, end=end))  # type: ignore[arg-type,no-any-return]

    def get_daily_gain(self) -> list[dict]:
        acct = self._select_account()
        return list(self._gateway.get_daily_gain(acct.get("id")))  # type: ignore[arg-type,no-any-return]

    # ------------------------------------------------------------------
    # Trading operations — refused (read-only source, fail-closed)
    # ------------------------------------------------------------------

    def submit_order(self, order: Order) -> OrderResult:
        return OrderResult(
            status=OrderStatus.FAILED,
            error="MyfxbookAdapter is read-only: cannot submit orders",
        )

    def cancel_order(self, broker_order_id: str) -> OrderResult:
        return OrderResult(
            status=OrderStatus.FAILED,
            error="MyfxbookAdapter is read-only: cannot cancel orders",
        )

    def get_order_status(self, broker_order_id: str) -> OrderResult:
        return OrderResult(
            status=OrderStatus.FAILED,
            error="MyfxbookAdapter is read-only: no order-status polling",
        )

    def close_position(self, broker_position_id: str, volume: float, symbol: str = "") -> OrderResult:
        return OrderResult(
            status=OrderStatus.FAILED,
            error="MyfxbookAdapter is read-only: cannot close positions",
        )

    def set_stop_loss(
        self,
        position_ticket: int,
        symbol: str,
        stop_loss_price: float,
        take_profit: float | None = None,
    ) -> bool:
        logger.warning("MyfxbookAdapter.set_stop_loss ignored (read-only source)")
        return False


def _to_float(value: object) -> float:
    """Best-effort float conversion; returns 0.0 on missing/garbage input."""
    if value is None or value == "":
        return 0.0
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0

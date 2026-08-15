"""Shadow Mode composite adapter for Quant OS.

Shadow Mode (``QuantConfig.shadow_mode``) connects to a real broker in
**read-only** fashion for live market data while executing orders against an
in-process ``PaperAdapter`` so that **no real orders are ever submitted**.

This adapter composes two underlying adapters:

* ``data_adapter``  — read-only MT5 (or any read-only source). Supplies live
  ``get_price`` / ``get_account_info``. All trading ops are refused by the
  underlying adapter's read-only guards.
* ``exec_adapter``  — ``PaperAdapter``. Receives the simulated fills. Live
  MT5 prices are pushed into it via ``set_price`` so P&L reflects real
  market conditions.

Why a composite instead of two adapters in ``BrokerManager``: the manager
exposes a single ``active`` adapter, but Shadow Mode needs *two* roles
(data vs execution) from one surface. Routing every call to the correct
underlying adapter here keeps the rest of the system (OrderManager,
reconciler, risk gate) unaware of the split.
"""

from __future__ import annotations

import logging

from .base import AccountInfo, BrokerAdapter, Order, OrderResult

logger = logging.getLogger(__name__)


class ShadowAdapter(BrokerAdapter):
    """Read-only data + paper execution, exposed as one ``BrokerAdapter``."""

    def __init__(self, data_adapter: BrokerAdapter, exec_adapter: BrokerAdapter) -> None:
        super().__init__("SHADOW")
        self._data = data_adapter
        self._exec = exec_adapter

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Connect both underlying adapters.

        Fails closed: if the live data source cannot connect we do NOT claim
        success, so ``BrokerManager.initialize`` can fall back to a pure
        paper adapter rather than silently running shadow mode with no data.
        """
        ok_data = False
        ok_exec = False
        try:
            ok_data = self._data.connect()
        except Exception as exc:  # noqa: BLE001
            logger.warning("ShadowAdapter data adapter connect failed: %s", exc)
        try:
            ok_exec = self._exec.connect()
        except Exception as exc:  # noqa: BLE001
            logger.warning("ShadowAdapter exec adapter connect failed: %s", exc)
        self._connected = ok_data and ok_exec
        return self._connected

    def disconnect(self) -> None:
        for adapter in (self._data, self._exec):
            try:
                adapter.disconnect()
            except Exception as exc:  # noqa: BLE001
                logger.warning("ShadowAdapter disconnect error: %s", exc)
        self._connected = False

    # ------------------------------------------------------------------
    # Data operations → read-only source
    # ------------------------------------------------------------------

    def get_account_info(self) -> AccountInfo:
        """Live account snapshot from the read-only data source.

        Used by the risk gate (OrderManager) so budget checks run against the
        real account equity, not a simulated one.
        """
        return self._data.get_account_info()

    def get_price(self, symbol: str) -> dict[str, float]:
        """Live bid/ask from the read-only data source."""
        return self._data.get_price(symbol)

    def get_positions(self) -> list[dict]:
        """Report the *simulated* paper positions, not the real broker book.

        In Shadow Mode we never trade the real account, so reconciling the
        real broker positions against our internal book would produce constant
        false drift (S-1). The simulated paper book is the correct source to
        compare against the internal engine positions.
        """
        return self._exec.get_positions()

    # ------------------------------------------------------------------
    # Execution operations → paper adapter (with live price sync)
    # ------------------------------------------------------------------

    def submit_order(self, order: Order) -> OrderResult:
        self._sync_price(order.symbol)
        return self._exec.submit_order(order)

    def cancel_order(self, broker_order_id: str) -> OrderResult:
        return self._exec.cancel_order(broker_order_id)

    def get_order_status(self, broker_order_id: str) -> OrderResult:
        return self._exec.get_order_status(broker_order_id)

    def close_position(self, broker_position_id: str, volume: float, symbol: str = "") -> OrderResult:
        self._sync_price(symbol or broker_position_id)
        return self._exec.close_position(broker_position_id, volume, symbol)

    def set_stop_loss(
        self,
        position_ticket: int,
        symbol: str,
        stop_loss_price: float,
        take_profit: float | None = None,
    ) -> bool:
        return self._exec.set_stop_loss(position_ticket, symbol, stop_loss_price, take_profit)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _sync_price(self, symbol: str) -> None:
        """Push the latest live price into the paper simulator (if supported)."""
        setter = getattr(self._exec, "set_price", None)
        if setter is None:
            return
        try:
            price = self._data.get_price(symbol)
            setter(symbol, price["bid"], price["ask"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("ShadowAdapter price sync failed for %s: %s", symbol, exc)

"""Canonical broker adapter interface and shared data types.

This module is the single source of truth for broker adapters in Quant OS.
The legacy module ``execution/broker_adapter.py`` is deprecated and exists
only for backward compatibility.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ...core.enums import OrderStatus


@dataclass
class Order:
    """Canonical order representation across all venues."""

    order_id: str
    signal_id: str
    symbol: str
    asset_class: str
    side: str  # "BUY" | "SELL"
    quantity: float
    stop_loss: float | None = None
    take_profit: float | None = None
    status: OrderStatus = OrderStatus.PENDING
    broker_order_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    trace_id: str = ""  # correlation ID for distributed tracing


@dataclass
class OrderResult:
    """Outcome returned by a broker adapter after attempting an order."""

    status: OrderStatus
    broker_id: str | None = None
    filled_quantity: float = 0.0
    avg_price: float = 0.0
    fee: float = 0.0
    error: str | None = None


@dataclass
class AccountInfo:
    """Snapshot of broker account state."""

    equity: float
    cash: float
    margin_used: float
    margin_available: float


class BrokerAdapter(ABC):
    """Abstract interface every venue adapter must implement."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._connected = False

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    def connect(self) -> bool:
        """Establish a connection to the broker API."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Tear down the connection to the broker API."""
        ...

    @property
    def is_connected(self) -> bool:
        """Return True if the adapter believes it is connected."""
        return self._connected

    # ------------------------------------------------------------------
    # Order and account operations
    # ------------------------------------------------------------------

    @abstractmethod
    def submit_order(self, order: Order) -> OrderResult:
        """Send an order to the broker and return the result.

        Must be idempotent: submitting the same ``order_id`` twice must not
        create a duplicate position.
        """
        ...

    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> OrderResult:
        """Cancel an open order by its broker-assigned ID."""
        ...

    @abstractmethod
    def get_positions(self) -> list[dict]:
        """Return all open positions at the broker."""
        ...

    @abstractmethod
    def get_order_status(self, broker_order_id: str) -> OrderResult:
        """Poll the current status of a single order."""
        ...

    @abstractmethod
    def close_position(self, broker_position_id: str, volume: float, symbol: str = "") -> OrderResult:
        """Close an open position by its broker-assigned ID.

        Args:
            broker_position_id: The broker's position ticket/ID.
            volume: Volume to close (partial or full).
            symbol: The instrument symbol (required by some brokers).

        Returns:
            ``OrderResult`` with the outcome of the close attempt.
        """
        ...

    @abstractmethod
    def set_stop_loss(
        self,
        position_ticket: int,
        symbol: str,
        stop_loss_price: float,
        take_profit: float | None = None,
    ) -> bool:
        """Set or modify the stop-loss (and optionally TP) on an open position."""
        ...

    @abstractmethod
    def get_account_info(self) -> AccountInfo:
        """Return a point-in-time snapshot of account balances."""
        ...

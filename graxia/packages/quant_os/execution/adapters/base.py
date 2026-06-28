"""Base broker adapter interface and shared data types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

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
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    broker_order_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class OrderResult:
    """Outcome returned by a broker adapter after attempting an order."""

    status: OrderStatus
    broker_id: Optional[str] = None
    filled_quantity: float = 0.0
    avg_price: float = 0.0
    error: Optional[str] = None


@dataclass
class AccountInfo:
    """Snapshot of broker account state."""

    equity: float
    cash: float
    margin_used: float
    margin_available: float


class BrokerAdapter(ABC):
    """Abstract interface every venue adapter must implement."""

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
    def get_account_info(self) -> AccountInfo:
        """Return a point-in-time snapshot of account balances."""
        ...

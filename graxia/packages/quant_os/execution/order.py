"""Order entity and state machine for Quant OS"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict, Any, Callable
from uuid import uuid4

from ..core.enums import OrderStatus, OrderSide, OrderType, TimeInForce
from ..core.exceptions import OrderStateError, ValidationError


@dataclass
class Order:
    """Order data class"""
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    time_in_force: TimeInForce = TimeInForce.DAY

    # IDs
    id: str = field(default_factory=lambda: str(uuid4()))
    client_order_id: str = field(default_factory=lambda: str(uuid4()))
    idempotency_key: str = ""
    broker_order_id: Optional[str] = None

    # Context
    strategy_id: str = ""
    signal_id: Optional[str] = None
    risk_check_id: Optional[str] = None
    approved_by: Optional[str] = None
    trading_mode: str = "PAPER"

    # State
    status: OrderStatus = OrderStatus.CREATED
    fill_quantity: Decimal = field(default_factory=lambda: Decimal("0"))
    avg_fill_price: Optional[Decimal] = None
    fee: Optional[Decimal] = None

    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None

    # Metadata
    rejection_reason: Optional[str] = None
    raw_broker_response: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if not self.idempotency_key:
            self.idempotency_key = self._generate_idempotency_key()

    def _generate_idempotency_key(self) -> str:
        """Generate idempotency key from order attributes"""
        key_data = f"{self.strategy_id}:{self.signal_id}:{self.symbol}:{self.side}:{self.quantity}:{self.created_at.timestamp() // 60}"
        import hashlib
        return hashlib.sha256(key_data.encode()).hexdigest()[:32]

    @property
    def is_filled(self) -> bool:
        return self.status == OrderStatus.FILLED

    @property
    def is_open(self) -> bool:
        return self.status in [
            OrderStatus.CREATED, OrderStatus.VALIDATED, OrderStatus.RISK_APPROVED,
            OrderStatus.COMPLIANCE_APPROVED, OrderStatus.PENDING_HUMAN,
            OrderStatus.SENT_TO_BROKER, OrderStatus.ACKNOWLEDGED, OrderStatus.PARTIAL_FILL
        ]

    @property
    def remaining_quantity(self) -> Decimal:
        return self.quantity - self.fill_quantity


class OrderStateMachine:
    """
    Order state machine with valid transitions.

    Valid transitions:
    CREATED → VALIDATED → RISK_APPROVED → COMPLIANCE_APPROVED → PENDING_HUMAN (MICRO only)
    PENDING_HUMAN → SENT_TO_BROKER
    COMPLIANCE_APPROVED → SENT_TO_BROKER (non-MICRO)
    SENT_TO_BROKER → ACKNOWLEDGED → PARTIAL_FILL/FILLED/REJECTED/CANCELLED/EXPIRED
    """

    VALID_TRANSITIONS: Dict[OrderStatus, list] = {
        OrderStatus.CREATED: [OrderStatus.VALIDATED, OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.ERROR],
        OrderStatus.VALIDATED: [OrderStatus.RISK_APPROVED, OrderStatus.REJECTED, OrderStatus.ERROR],
        OrderStatus.RISK_APPROVED: [OrderStatus.COMPLIANCE_APPROVED, OrderStatus.REJECTED, OrderStatus.ERROR],
        OrderStatus.COMPLIANCE_APPROVED: [
            OrderStatus.PENDING_HUMAN, OrderStatus.SENT_TO_BROKER,
            OrderStatus.REJECTED, OrderStatus.ERROR
        ],
        OrderStatus.PENDING_HUMAN: [
            OrderStatus.SENT_TO_BROKER, OrderStatus.CANCELLED, OrderStatus.EXPIRED, OrderStatus.ERROR
        ],
        OrderStatus.SENT_TO_BROKER: [
            OrderStatus.ACKNOWLEDGED, OrderStatus.REJECTED, OrderStatus.ERROR
        ],
        OrderStatus.ACKNOWLEDGED: [
            OrderStatus.PARTIAL_FILL, OrderStatus.FILLED, OrderStatus.CANCELLED,
            OrderStatus.EXPIRED, OrderStatus.ERROR
        ],
        OrderStatus.PARTIAL_FILL: [
            OrderStatus.PARTIAL_FILL, OrderStatus.FILLED, OrderStatus.CANCELLED,
            OrderStatus.EXPIRED, OrderStatus.ERROR
        ],
        OrderStatus.CANCEL_REQUESTED: [OrderStatus.CANCELLED, OrderStatus.FILLED, OrderStatus.ERROR],
    }

    TERMINAL_STATES = [
        OrderStatus.FILLED, OrderStatus.REJECTED, OrderStatus.CANCELLED,
        OrderStatus.EXPIRED, OrderStatus.ERROR
    ]

    def __init__(self, order: Order):
        self.order = order
        self._transition_handlers: Dict[OrderStatus, list] = {}

    def can_transition(self, new_status: OrderStatus) -> bool:
        """Check if transition is valid"""
        if self.order.status in self.TERMINAL_STATES:
            return False

        valid_next = self.VALID_TRANSITIONS.get(self.order.status, [])
        return new_status in valid_next

    def transition(self, new_status: OrderStatus, reason: str = "", actor: str = "system") -> bool:
        """
        Attempt state transition.
        Returns True if successful, raises OrderStateError if invalid.
        """
        if not self.can_transition(new_status):
            raise OrderStateError(
                f"Invalid transition: {self.order.status.value} → {new_status.value}",
                from_state=self.order.status.value,
                to_state=new_status.value,
                context={"order_id": self.order.id, "reason": reason}
            )

        old_status = self.order.status
        self.order.status = new_status
        self.order.updated_at = datetime.now(timezone.utc)

        # Update timestamp for specific states
        if new_status == OrderStatus.SENT_TO_BROKER:
            self.order.sent_at = datetime.now(timezone.utc)
        elif new_status == OrderStatus.FILLED:
            self.order.filled_at = datetime.now(timezone.utc)

        # Call transition handlers
        self._call_handlers(new_status, old_status, reason, actor)

        return True

    def on_transition(self, status: OrderStatus, handler: Callable):
        """Register a handler for a specific status transition"""
        if status not in self._transition_handlers:
            self._transition_handlers[status] = []
        self._transition_handlers[status].append(handler)

    def _call_handlers(self, new_status: OrderStatus, old_status: OrderStatus, reason: str, actor: str):
        """Call registered handlers for the transition"""
        handlers = self._transition_handlers.get(new_status, [])
        for handler in handlers:
            try:
                handler(self.order, old_status, new_status, reason, actor)
            except Exception as e:
                # Log but don't fail the transition
                print(f"Handler error: {e}")

    def validate_order(self) -> None:
        """Validate order before submission"""
        errors = []

        if not self.order.symbol or len(self.order.symbol) < 3:
            errors.append("Invalid symbol")

        if self.order.quantity <= 0:
            errors.append("Quantity must be positive")

        if self.order.order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT] and self.order.price is None:
            errors.append("Limit orders require price")

        if self.order.order_type in [OrderType.STOP, OrderType.STOP_LIMIT] and self.order.stop_price is None:
            errors.append("Stop orders require stop price")

        if errors:
            raise ValidationError("Order validation failed", context={"errors": errors})

    def approve_human(self, approver: str) -> None:
        """Human approval for MICRO mode"""
        if self.order.status != OrderStatus.PENDING_HUMAN:
            raise OrderStateError(
                "Order not in PENDING_HUMAN state",
                from_state=self.order.status.value,
                to_state=OrderStatus.SENT_TO_BROKER.value
            )

        self.order.approved_by = approver
        self.transition(OrderStatus.SENT_TO_BROKER, f"Approved by {approver}", approver)

    def reject(self, reason: str, actor: str = "system") -> None:
        """Reject order"""
        self.order.rejection_reason = reason
        self.transition(OrderStatus.REJECTED, reason, actor)

    def fill(self, fill_quantity: Decimal, fill_price: Decimal, fee: Decimal = Decimal("0")) -> None:
        """Record a fill"""
        self.order.fill_quantity += fill_quantity

        # Calculate average fill price
        if self.order.avg_fill_price is None:
            self.order.avg_fill_price = fill_price
        else:
            total_qty = self.order.fill_quantity
            prev_qty = total_qty - fill_quantity
            self.order.avg_fill_price = (
                (self.order.avg_fill_price * prev_qty + fill_price * fill_quantity) / total_qty
            )

        # Update fee
        if self.order.fee is None:
            self.order.fee = fee
        else:
            self.order.fee += fee

        # Determine new status
        if self.order.fill_quantity >= self.order.quantity:
            self.transition(OrderStatus.FILLED, f"Filled {fill_quantity} @ {fill_price}")
        else:
            self.transition(OrderStatus.PARTIAL_FILL, f"Partial fill {fill_quantity} @ {fill_price}")

    def cancel(self, reason: str = "", actor: str = "system") -> None:
        """Cancel order"""
        if self.order.status in [OrderStatus.CREATED, OrderStatus.VALIDATED,
                                  OrderStatus.RISK_APPROVED, OrderStatus.COMPLIANCE_APPROVED,
                                  OrderStatus.PENDING_HUMAN]:
            self.transition(OrderStatus.CANCELLED, reason or "Cancelled before submission", actor)
        elif self.order.is_open and self.order.status not in self.TERMINAL_STATES:
            self.transition(OrderStatus.CANCEL_REQUESTED, "Cancellation requested", actor)
        else:
            raise OrderStateError(
                f"Cannot cancel order in {self.order.status.value} state",
                from_state=self.order.status.value,
                to_state=OrderStatus.CANCELLED.value
            )

    def expire(self, reason: str = "Order expired") -> None:
        """Expire order (for MICRO mode timeout)"""
        if self.order.status == OrderStatus.PENDING_HUMAN:
            self.transition(OrderStatus.EXPIRED, reason)
        else:
            raise OrderStateError(
                f"Cannot expire order in {self.order.status.value} state",
                from_state=self.order.status.value,
                to_state=OrderStatus.EXPIRED.value
            )


def create_order(
    symbol: str,
    side: OrderSide,
    order_type: OrderType,
    quantity: Decimal,
    price: Optional[Decimal] = None,
    stop_price: Optional[Decimal] = None,
    strategy_id: str = "",
    signal_id: Optional[str] = None,
    trading_mode: str = "PAPER",
    time_in_force: TimeInForce = TimeInForce.DAY
) -> Order:
    """Factory function to create a new order"""
    return Order(
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        price=price,
        stop_price=stop_price,
        strategy_id=strategy_id,
        signal_id=signal_id,
        trading_mode=trading_mode,
        time_in_force=time_in_force
    )

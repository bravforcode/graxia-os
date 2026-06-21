"""
Order lifecycle state machine per Master Plan Section 14.3.

Tracks full lifecycle from signal creation through audit — distinct from
execution/order.py OrderStateMachine which handles broker-level states.

For BACKTEST and SHADOW lifecycle tracking, not live execution.
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime

from ..core.exceptions import OrderStateError


class OrderState(Enum):
    SIGNAL_CREATED = "SIGNAL_CREATED"
    RISK_CHECKED = "RISK_CHECKED"
    ORDER_PRECHECKED = "ORDER_PRECHECKED"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_ACKNOWLEDGED = "ORDER_ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    PROTECTIVE_STOPS_VERIFIED = "PROTECTIVE_STOPS_VERIFIED"
    POSITION_RECONCILED = "POSITION_RECONCILED"
    CLOSED = "CLOSED"
    DEAL_RECONCILED = "DEAL_RECONCILED"
    AUDITED = "AUDITED"
    CRITICAL_INCIDENT = "CRITICAL_INCIDENT"


# Valid transitions per Master Plan Section 14.3
TRANSITIONS: dict[OrderState, list[OrderState]] = {
    OrderState.SIGNAL_CREATED: [OrderState.RISK_CHECKED, OrderState.REJECTED],
    OrderState.RISK_CHECKED: [OrderState.ORDER_PRECHECKED, OrderState.REJECTED],
    OrderState.ORDER_PRECHECKED: [OrderState.ORDER_SUBMITTED, OrderState.REJECTED],
    OrderState.ORDER_SUBMITTED: [OrderState.ORDER_ACKNOWLEDGED, OrderState.REJECTED, OrderState.EXPIRED],
    OrderState.ORDER_ACKNOWLEDGED: [OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.REJECTED, OrderState.EXPIRED],
    OrderState.PARTIALLY_FILLED: [OrderState.FILLED, OrderState.REJECTED, OrderState.EXPIRED],
    OrderState.FILLED: [OrderState.PROTECTIVE_STOPS_VERIFIED, OrderState.CRITICAL_INCIDENT],
    OrderState.PROTECTIVE_STOPS_VERIFIED: [OrderState.POSITION_RECONCILED],
    OrderState.POSITION_RECONCILED: [OrderState.CLOSED],
    OrderState.CLOSED: [OrderState.DEAL_RECONCILED],
    OrderState.DEAL_RECONCILED: [OrderState.AUDITED],
    OrderState.CRITICAL_INCIDENT: [],  # Terminal — no auto-recovery
    OrderState.REJECTED: [],           # Terminal
    OrderState.EXPIRED: [],            # Terminal
    OrderState.AUDITED: [],            # Terminal (success)
}

VALID_TRANSITIONS = TRANSITIONS  # alias for __init__.py compat

TERMINAL_STATES = {OrderState.CRITICAL_INCIDENT, OrderState.REJECTED, OrderState.EXPIRED, OrderState.AUDITED}


@dataclass
class OrderStateMachine:
    """Tracks the full lifecycle of a single order through all states."""
    order_id: str
    state: OrderState = OrderState.SIGNAL_CREATED
    history: list[dict] = field(default_factory=list)

    def transition(self, new_state: OrderState, reason: str = "") -> bool:
        """Attempt transition. Returns True if valid, raises OrderStateError if invalid."""
        allowed = TRANSITIONS.get(self.state, [])
        if new_state not in allowed:
            raise OrderStateError(
                f"Invalid lifecycle transition: {self.state.value} → {new_state.value}",
                from_state=self.state.value,
                to_state=new_state.value,
                context={"order_id": self.order_id, "reason": reason},
            )
        self.history.append({
            "from": self.state.value,
            "to": new_state.value,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
        })
        self.state = new_state
        return True

    def is_terminal(self) -> bool:
        """Check if order is in a terminal state."""
        return self.state in TERMINAL_STATES

    def needs_critical_response(self) -> bool:
        """Check if CRITICAL_INCIDENT was reached without PROTECTIVE_STOPS_VERIFIED."""
        if self.state != OrderState.CRITICAL_INCIDENT:
            return False
        visited = {h["to"] for h in self.history}
        return OrderState.PROTECTIVE_STOPS_VERIFIED.value not in visited

    # ── Spec-named aliases ────────────────────────────────────────────────
    # ponytail: aliases so tests import canonical names without breaking existing API

    def advance(self, new_state: OrderState, reason: str = "") -> bool:
        """Alias for transition."""
        return self.transition(new_state, reason)

    def needs_protective_stop_verification(self) -> bool:
        """Alias for needs_critical_response."""
        return self.needs_critical_response()

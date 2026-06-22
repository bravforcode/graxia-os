"""Order state machine — 16 states, enforced transitions, no MT5 dependency."""

from enum import Enum

from ..core.exceptions import OrderStateError


class OrderState(Enum):
    SIGNAL_CREATED = "signal_created"
    RISK_CHECKED = "risk_checked"
    ORDER_PRECHECKED = "order_prechecked"
    ORDER_SUBMITTED = "order_submitted"
    ORDER_ACKNOWLEDGED = "order_acknowledged"
    PARTIAL_FILL = "partial_fill"
    FILLED = "filled"
    PROTECTIVE_STOPS_PENDING = "protective_stops_pending"
    PROTECTIVE_STOPS_VERIFIED = "protective_stops_verified"
    POSITION_RECONCILED = "position_reconciled"
    CLOSED = "closed"
    DEAL_RECONCILED = "deal_reconciled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    AUDITED = "audited"
    CRITICAL_INCIDENT = "critical_incident"


TRANSITIONS: dict[OrderState, set[OrderState]] = {
    OrderState.SIGNAL_CREATED: {
        OrderState.RISK_CHECKED, OrderState.REJECTED, OrderState.CRITICAL_INCIDENT,
    },
    OrderState.RISK_CHECKED: {
        OrderState.ORDER_PRECHECKED, OrderState.REJECTED, OrderState.CRITICAL_INCIDENT,
    },
    OrderState.ORDER_PRECHECKED: {
        OrderState.ORDER_SUBMITTED, OrderState.REJECTED, OrderState.CRITICAL_INCIDENT,
    },
    OrderState.ORDER_SUBMITTED: {
        OrderState.ORDER_ACKNOWLEDGED, OrderState.PARTIAL_FILL,
        OrderState.REJECTED, OrderState.EXPIRED, OrderState.CRITICAL_INCIDENT,
    },
    OrderState.ORDER_ACKNOWLEDGED: {
        OrderState.FILLED, OrderState.PARTIAL_FILL,
        OrderState.REJECTED, OrderState.EXPIRED, OrderState.CRITICAL_INCIDENT,
    },
    OrderState.PARTIAL_FILL: {
        OrderState.FILLED, OrderState.CRITICAL_INCIDENT,
    },
    OrderState.FILLED: {
        OrderState.PROTECTIVE_STOPS_PENDING, OrderState.PROTECTIVE_STOPS_VERIFIED,
        OrderState.CRITICAL_INCIDENT,
    },
    OrderState.PROTECTIVE_STOPS_PENDING: {
        OrderState.PROTECTIVE_STOPS_VERIFIED, OrderState.CRITICAL_INCIDENT,
    },
    OrderState.PROTECTIVE_STOPS_VERIFIED: {
        OrderState.POSITION_RECONCILED, OrderState.CRITICAL_INCIDENT,
    },
    OrderState.POSITION_RECONCILED: {
        OrderState.CLOSED, OrderState.CRITICAL_INCIDENT,
    },
    OrderState.CLOSED: {
        OrderState.DEAL_RECONCILED, OrderState.CRITICAL_INCIDENT,
    },
    OrderState.DEAL_RECONCILED: {
        OrderState.AUDITED, OrderState.CRITICAL_INCIDENT,
    },
    OrderState.REJECTED: set(),
    OrderState.EXPIRED: set(),
    OrderState.AUDITED: set(),
    OrderState.CRITICAL_INCIDENT: set(),
}

TERMINAL_STATES = frozenset({
    OrderState.REJECTED, OrderState.EXPIRED,
    OrderState.AUDITED, OrderState.CRITICAL_INCIDENT,
})


class OrderStateMachine:
    __slots__ = ("order_id", "_state", "_history")

    def __init__(self, order_id: str = "", initial: OrderState = OrderState.SIGNAL_CREATED) -> None:
        self.order_id = order_id
        self._state = initial
        self._history: list[OrderState] = [initial]

    @property
    def state(self) -> OrderState:
        return self._state

    def advance(self, target: OrderState, reason: str = "") -> bool:
        self.transition(target, reason)
        return True

    def transition(self, target: OrderState, reason: str = "") -> None:
        allowed = TRANSITIONS.get(self._state, set())
        if target not in allowed:
            raise OrderStateError(
                f"Invalid transition: {self._state.value} -> {target.value}",
                from_state=self._state.value,
                to_state=target.value,
            )
        self._state = target
        self._history.append(target)

    def is_terminal(self) -> bool:
        return self._state in TERMINAL_STATES

    def needs_protective_stop_verification(self) -> bool:
        return self._state == OrderState.PROTECTIVE_STOPS_PENDING

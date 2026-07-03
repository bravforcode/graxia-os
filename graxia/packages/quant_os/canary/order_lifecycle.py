"""Phase BE-P9 — Order lifecycle state machine."""

from enum import Enum


class OrderState(Enum):
    SIGNAL_CREATED = "SIGNAL_CREATED"
    RISK_ACCEPTED = "RISK_ACCEPTED"
    ORDER_INTENT_CREATED = "ORDER_INTENT_CREATED"
    ORDER_CHECKED = "ORDER_CHECKED"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    BROKER_ACKNOWLEDGED = "BROKER_ACKNOWLEDGED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    PROTECTIVE_STOPS_VERIFIED = "PROTECTIVE_STOPS_VERIFIED"
    POSITION_RECONCILED = "POSITION_RECONCILED"
    CLOSED = "CLOSED"
    DEAL_RECONCILED = "DEAL_RECONCILED"
    AUDITED = "AUDITED"


VALID_TRANSITIONS = {
    OrderState.SIGNAL_CREATED: [OrderState.RISK_ACCEPTED, OrderState.REJECTED],
    OrderState.RISK_ACCEPTED: [OrderState.ORDER_INTENT_CREATED, OrderState.REJECTED],
    OrderState.ORDER_INTENT_CREATED: [OrderState.ORDER_CHECKED],
    OrderState.ORDER_CHECKED: [OrderState.ORDER_SUBMITTED, OrderState.REJECTED],
    OrderState.ORDER_SUBMITTED: [OrderState.BROKER_ACKNOWLEDGED, OrderState.REJECTED],
    OrderState.BROKER_ACKNOWLEDGED: [
        OrderState.FILLED,
        OrderState.PARTIALLY_FILLED,
        OrderState.REJECTED,
        OrderState.EXPIRED,
    ],
    OrderState.FILLED: [OrderState.PROTECTIVE_STOPS_VERIFIED],
    OrderState.PARTIALLY_FILLED: [OrderState.PROTECTIVE_STOPS_VERIFIED, OrderState.CLOSED],
    OrderState.PROTECTIVE_STOPS_VERIFIED: [OrderState.POSITION_RECONCILED],
    OrderState.POSITION_RECONCILED: [OrderState.CLOSED],
    OrderState.CLOSED: [OrderState.DEAL_RECONCILED],
    OrderState.DEAL_RECONCILED: [OrderState.AUDITED],
}


class OrderLifecycle:
    """Order lifecycle state machine."""

    def __init__(self):
        self._state = OrderState.SIGNAL_CREATED
        self._history: list[OrderState] = [OrderState.SIGNAL_CREATED]

    def get_state(self) -> OrderState:
        return self._state

    def transition(self, target: OrderState) -> bool:
        """Attempt transition. Returns True if valid."""
        valid = VALID_TRANSITIONS.get(self._state, [])
        if target in valid:
            self._state = target
            self._history.append(target)
            return True
        return False

    def get_history(self) -> list[OrderState]:
        return self._history.copy()

    def is_terminal(self) -> bool:
        return self._state in (OrderState.AUDITED, OrderState.REJECTED, OrderState.EXPIRED)

    def is_filled(self) -> bool:
        return self._state in (
            OrderState.FILLED,
            OrderState.PARTIALLY_FILLED,
            OrderState.PROTECTIVE_STOPS_VERIFIED,
            OrderState.POSITION_RECONCILED,
            OrderState.CLOSED,
            OrderState.DEAL_RECONCILED,
            OrderState.AUDITED,
        )

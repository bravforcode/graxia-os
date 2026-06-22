from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import hashlib
import json

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
    CRITICAL_INCIDENT = "CRITICAL_INCIDENT"

VALID_TRANSITIONS = {
    OrderState.SIGNAL_CREATED: [OrderState.RISK_ACCEPTED, OrderState.CRITICAL_INCIDENT],
    OrderState.RISK_ACCEPTED: [OrderState.ORDER_INTENT_CREATED, OrderState.CRITICAL_INCIDENT],
    OrderState.ORDER_INTENT_CREATED: [OrderState.ORDER_CHECKED, OrderState.CRITICAL_INCIDENT],
    OrderState.ORDER_CHECKED: [OrderState.ORDER_SUBMITTED, OrderState.CRITICAL_INCIDENT],
    OrderState.ORDER_SUBMITTED: [OrderState.BROKER_ACKNOWLEDGED, OrderState.REJECTED, OrderState.EXPIRED, OrderState.CRITICAL_INCIDENT],
    OrderState.BROKER_ACKNOWLEDGED: [OrderState.FILLED, OrderState.PARTIALLY_FILLED, OrderState.REJECTED, OrderState.EXPIRED, OrderState.CRITICAL_INCIDENT],
    OrderState.FILLED: [OrderState.PROTECTIVE_STOPS_VERIFIED, OrderState.CRITICAL_INCIDENT],
    OrderState.PARTIALLY_FILLED: [OrderState.PROTECTIVE_STOPS_VERIFIED, OrderState.CRITICAL_INCIDENT],
    OrderState.PROTECTIVE_STOPS_VERIFIED: [OrderState.POSITION_RECONCILED, OrderState.CRITICAL_INCIDENT],
    OrderState.POSITION_RECONCILED: [OrderState.CLOSED, OrderState.CRITICAL_INCIDENT],
    OrderState.CLOSED: [OrderState.DEAL_RECONCILED, OrderState.CRITICAL_INCIDENT],
    OrderState.DEAL_RECONCILED: [OrderState.AUDITED, OrderState.CRITICAL_INCIDENT],
    OrderState.AUDITED: [],
    OrderState.CRITICAL_INCIDENT: [],
    OrderState.REJECTED: [],
    OrderState.EXPIRED: [],
}

TERMINAL_STATES = {OrderState.AUDITED, OrderState.CRITICAL_INCIDENT, OrderState.REJECTED, OrderState.EXPIRED}

@dataclass
class OrderTransition:
    from_state: OrderState
    to_state: OrderState
    timestamp: datetime
    reason: str = ""

@dataclass
class CanaryOrder:
    order_id: str
    symbol: str
    direction: str
    volume: float
    entry_price: float
    stop_loss: float
    take_profit: Optional[float]
    strategy_id: str
    state: OrderState = OrderState.SIGNAL_CREATED
    transitions: list[OrderTransition] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def transition(self, to_state: OrderState, reason: str = "") -> tuple[bool, str]:
        valid_targets = VALID_TRANSITIONS.get(self.state, [])
        if to_state not in valid_targets:
            return False, f"INVALID_TRANSITION:{self.state.value}->{to_state.value}"

        if self.state in TERMINAL_STATES:
            return False, f"TERMINAL_STATE:{self.state.value}"

        self.transitions.append(OrderTransition(
            from_state=self.state,
            to_state=to_state,
            timestamp=datetime.utcnow(),
            reason=reason,
        ))
        self.state = to_state
        return True, "TRANSITIONED"

    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    def history(self) -> list[str]:
        return [f"{t.from_state.value}->{t.to_state.value}" for t in self.transitions]

    def fingerprint(self) -> str:
        data = json.dumps({
            "order_id": self.order_id,
            "state": self.state.value,
            "transitions": len(self.transitions),
        }, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "volume": self.volume,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "strategy_id": self.strategy_id,
            "state": self.state.value,
            "transitions": len(self.transitions),
            "created_at": self.created_at.isoformat(),
        }

class PostFillVerifier:
    """Post-fill mandatory verification."""

    def verify_fill_price(self, expected: float, actual: float, tolerance: float = 0.01) -> tuple[bool, str]:
        diff = abs(expected - actual)
        if diff > tolerance:
            return False, f"FILL_MISMATCH:expected={expected},actual={actual},diff={diff}"
        return True, "FILL_VERIFIED"

    def verify_sl_tp_exists(self, broker_sl: float, broker_tp: Optional[float],
                            expected_sl: float, expected_tp: Optional[float]) -> tuple[bool, str]:
        if broker_sl != expected_sl:
            return False, f"SL_MISMATCH:broker={broker_sl},expected={expected_sl}"
        if expected_tp and broker_tp != expected_tp:
            return False, f"TP_MISMATCH:broker={broker_tp},expected={expected_tp}"
        return True, "SL_TP_VERIFIED"

    def verify_position_state(self, has_position: bool, expected_direction: str,
                               actual_direction: str) -> tuple[bool, str]:
        if not has_position:
            return False, "NO_POSITION_FOUND"
        if actual_direction != expected_direction:
            return False, f"DIRECTION_MISMATCH:expected={expected_direction},actual={actual_direction}"
        return True, "POSITION_VERIFIED"

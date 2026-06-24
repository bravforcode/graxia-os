"""Canary state machine. All transitions explicit."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4
import hashlib, json

from execution.demo_canary.enums import CanaryState, CanaryActor
from execution.demo_canary.errors import StateTransitionError

# Allowed transitions: {from_state: [(to_state, required_actor, reason_code)]}
ALLOWED_TRANSITIONS = {
    CanaryState.DRAFT: [
        (CanaryState.PROFILE_VERIFIED, CanaryActor.SYSTEM, "PROFILE_GUARD_PASSED"),
        (CanaryState.REJECTED, CanaryActor.SYSTEM, "PROFILE_GUARD_FAILED"),
    ],
    CanaryState.PROFILE_VERIFIED: [
        (CanaryState.CONTRACT_VERIFIED, CanaryActor.SYSTEM, "CONTRACT_SPEC_RESOLVED"),
        (CanaryState.REJECTED, CanaryActor.SYSTEM, "CONTRACT_SPEC_FAILED"),
    ],
    CanaryState.CONTRACT_VERIFIED: [
        (CanaryState.MARKET_DATA_VERIFIED, CanaryActor.SYSTEM, "MARKET_DATA_FRESH"),
        (CanaryState.REJECTED, CanaryActor.SYSTEM, "MARKET_DATA_STALE"),
    ],
    CanaryState.MARKET_DATA_VERIFIED: [
        (CanaryState.RISK_VERIFIED, CanaryActor.SYSTEM, "RISK_CHECKS_PASSED"),
        (CanaryState.REJECTED, CanaryActor.SYSTEM, "RISK_CHECKS_FAILED"),
    ],
    CanaryState.RISK_VERIFIED: [
        (CanaryState.PREFLIGHT_PASSED, CanaryActor.SYSTEM, "PREFLIGHT_PASSED"),
        (CanaryState.REJECTED, CanaryActor.SYSTEM, "PREFLIGHT_FAILED"),
    ],
    CanaryState.PREFLIGHT_PASSED: [
        (CanaryState.AWAITING_HUMAN_APPROVAL, CanaryActor.SYSTEM, "PLAN_SEALED_FOR_APPROVAL"),
    ],
    CanaryState.AWAITING_HUMAN_APPROVAL: [
        (CanaryState.APPROVED, CanaryActor.OPERATOR, "HUMAN_APPROVED"),
        (CanaryState.REJECTED, CanaryActor.OPERATOR, "HUMAN_REJECTED"),
        (CanaryState.EXPIRED, CanaryActor.SYSTEM, "APPROVAL_TTL_EXPIRED"),
    ],
    CanaryState.APPROVED: [
        (CanaryState.EXECUTION_MUTEX_HELD, CanaryActor.SYSTEM, "MUTEX_ACQUIRED"),
        (CanaryState.REJECTED, CanaryActor.SYSTEM, "MUTEX_FAILED"),
    ],
    CanaryState.EXECUTION_MUTEX_HELD: [
        (CanaryState.SUBMITTING, CanaryActor.SYSTEM, "FINAL_FRESHNESS_CHECK_PASSED"),
        (CanaryState.DRY_RUN_SEND_BLOCKED, CanaryActor.SYSTEM, "DRY_RUN_MODE_SEND_BLOCKED"),
    ],
    # Post-submit states
    CanaryState.SUBMITTING: [
        (CanaryState.SUBMISSION_RECEIPT_RECORDED, CanaryActor.BROKER, "ORDER_SUBMITTED"),
        (CanaryState.SUBMISSION_UNKNOWN, CanaryActor.SYSTEM, "ORDER_SEND_RETURNED_NONE"),
        (CanaryState.SUBMITTED, CanaryActor.SYSTEM, "ORDER_SEND_SUCCESS"),
        (CanaryState.REJECTED, CanaryActor.BROKER, "ORDER_SEND_REJECTED"),
    ],
    CanaryState.SUBMISSION_RECEIPT_RECORDED: [(CanaryState.POSITION_RECONCILING, CanaryActor.SYSTEM, "RECONCILING")],
    # Terminal/blocked states — no outgoing transitions
}

@dataclass
class StateEvent:
    event_id: str = ""
    canary_id: str = ""
    timestamp_utc: str = ""
    previous_state: str = ""
    next_state: str = ""
    actor_type: str = ""
    reason_code: str = ""
    input_hash: str = ""
    output_hash: str = ""

class CanaryStateMachine:
    def __init__(self, canary_id: str):
        self.canary_id = canary_id
        self._state = CanaryState.DRAFT
        self._history: list[StateEvent] = []

    @property
    def state(self) -> CanaryState:
        return self._state

    def transition(self, to_state: CanaryState, actor: CanaryActor, reason_code: str = "", input_hash: str = "", output_hash: str = "") -> StateEvent:
        """Attempt transition. Raises StateTransitionError if not allowed."""
        allowed = ALLOWED_TRANSITIONS.get(self._state, [])
        valid = any(to == to_state and a == actor for to, a, _ in allowed)

        if not valid:
            allowed_str = ", ".join(f"{s.value}({a.value})" for s, a, _ in allowed)
            raise StateTransitionError(
                f"Cannot transition from {self._state.value} to {to_state.value} "
                f"with actor {actor.value}. Allowed: [{allowed_str}]"
            )

        event = StateEvent(
            event_id=str(uuid4()),
            canary_id=self.canary_id,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            previous_state=self._state.value,
            next_state=to_state.value,
            actor_type=actor.value,
            reason_code=reason_code,
            input_hash=input_hash,
            output_hash=output_hash,
        )

        self._state = to_state
        self._history.append(event)
        return event

    def is_terminal(self) -> bool:
        return self._state in {
            CanaryState.REJECTED, CanaryState.EXPIRED, CanaryState.KILLED,
            CanaryState.SEALED, CanaryState.RECOVERY_REQUIRED,
            CanaryState.SUBMISSION_UNKNOWN,
        }

    def is_pre_submit(self) -> bool:
        pre_submit_states = {
            CanaryState.DRAFT, CanaryState.PROFILE_VERIFIED, CanaryState.CONTRACT_VERIFIED,
            CanaryState.MARKET_DATA_VERIFIED, CanaryState.RISK_VERIFIED,
            CanaryState.PREFLIGHT_PASSED, CanaryState.AWAITING_HUMAN_APPROVAL,
            CanaryState.APPROVED, CanaryState.EXECUTION_MUTEX_HELD,
        }
        return self._state in pre_submit_states

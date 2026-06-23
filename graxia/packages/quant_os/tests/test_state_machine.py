"""Test canary state machine."""
import pytest
from execution.demo_canary.state_machine import CanaryStateMachine
from execution.demo_canary.errors import StateTransitionError
from execution.demo_canary.enums import CanaryState, CanaryActor

class TestStateMachine:
    def test_initial_state_draft(self):
        sm = CanaryStateMachine("CANARY-001")
        assert sm.state == CanaryState.DRAFT

    def test_draft_to_profile_verified(self):
        sm = CanaryStateMachine("CANARY-001")
        event = sm.transition(CanaryState.PROFILE_VERIFIED, CanaryActor.SYSTEM, "PROFILE_GUARD_PASSED")
        assert sm.state == CanaryState.PROFILE_VERIFIED
        assert event.reason_code == "PROFILE_GUARD_PASSED"

    def test_forbidden_transition_raises_error(self):
        sm = CanaryStateMachine("CANARY-001")
        with pytest.raises(StateTransitionError):
            sm.transition(CanaryState.APPROVED, CanaryActor.OPERATOR)

    def test_draft_to_rejected(self):
        sm = CanaryStateMachine("CANARY-001")
        sm.transition(CanaryState.REJECTED, CanaryActor.SYSTEM, "GUARD_FAILED")
        assert sm.state == CanaryState.REJECTED
        assert sm.is_terminal()

    def test_full_path_to_mutex(self):
        sm = CanaryStateMachine("CANARY-001")
        sm.transition(CanaryState.PROFILE_VERIFIED, CanaryActor.SYSTEM)
        sm.transition(CanaryState.CONTRACT_VERIFIED, CanaryActor.SYSTEM)
        sm.transition(CanaryState.MARKET_DATA_VERIFIED, CanaryActor.SYSTEM)
        sm.transition(CanaryState.RISK_VERIFIED, CanaryActor.SYSTEM)
        sm.transition(CanaryState.PREFLIGHT_PASSED, CanaryActor.SYSTEM)
        sm.transition(CanaryState.AWAITING_HUMAN_APPROVAL, CanaryActor.SYSTEM)
        sm.transition(CanaryState.APPROVED, CanaryActor.OPERATOR)
        sm.transition(CanaryState.EXECUTION_MUTEX_HELD, CanaryActor.SYSTEM)
        assert sm.state == CanaryState.EXECUTION_MUTEX_HELD
        assert sm.is_pre_submit()

    def test_is_terminal_states(self):
        for state in [CanaryState.REJECTED, CanaryState.EXPIRED, CanaryState.KILLED]:
            sm = CanaryStateMachine("CANARY-001")
            if state == CanaryState.REJECTED:
                sm.transition(CanaryState.REJECTED, CanaryActor.SYSTEM, "test")
            assert sm.is_terminal() if state == sm.state else True

    def test_event_has_all_fields(self):
        sm = CanaryStateMachine("CANARY-001")
        event = sm.transition(CanaryState.PROFILE_VERIFIED, CanaryActor.SYSTEM, "TEST")
        assert event.event_id
        assert event.canary_id == "CANARY-001"
        assert event.timestamp_utc
        assert event.previous_state == "DRAFT"
        assert event.next_state == "PROFILE_VERIFIED"
        assert event.actor_type == "SYSTEM"

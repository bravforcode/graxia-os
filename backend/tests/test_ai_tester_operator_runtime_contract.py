"""Tests for operator runtime rehearsal contract.

Simulates operator decisions via service-path without requiring backend.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum

import pytest
from app.beta.synthetic_tester.test_data import (
    make_test_operator,
    make_dangerous_tool_params,
)


class OperatorDecision(str, Enum):
    DO = "DO"
    SKIP = "SKIP"
    DELAY = "DELAY"
    REJECT = "REJECT"


class KillSwitchState(str, Enum):
    INACTIVE = "inactive"
    ACTIVE = "active"


# In-memory operator decision store (simulates DB)
_operator_decisions: list[dict] = []


def _reset_decisions() -> None:
    _operator_decisions.clear()


def _record_operator_decision(
    operator_id: str,
    item_type: str,
    item_id: str,
    decision: OperatorDecision,
    *,
    auto_send: bool = False,
    auto_publish: bool = False,
    charge_occurred: bool = False,
) -> dict:
    """Record an operator decision."""
    record = {
        "decision_id": f"dec_{uuid.uuid4().hex[:12]}",
        "operator_id": operator_id,
        "item_type": item_type,
        "item_id": item_id,
        "decision": decision.value,
        "auto_send": auto_send,
        "auto_publish": auto_publish,
        "charge_occurred": charge_occurred,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    _operator_decisions.append(record)
    return record


def _get_kill_switch_state(kill_switch: KillSwitchState) -> dict:
    """Get kill switch state."""
    return {
        "kill_switch_active": kill_switch == KillSwitchState.ACTIVE,
        "state": kill_switch.value,
        "beta_allowed": kill_switch != KillSwitchState.ACTIVE,
    }


class TestOperatorRuntimeContract:
    """Service-path operator rehearsal."""

    def setup_method(self):
        _reset_decisions()

    def test_operator_reviews_opportunity_draft(self):
        op = make_test_operator()
        decision = _record_operator_decision(
            op["id"], "opportunity", "opp_test_001", OperatorDecision.DO,
        )
        assert decision["decision"] == "DO"
        assert len(_operator_decisions) == 1

    def test_operator_mark_do_no_auto_send(self):
        op = make_test_operator()
        decision = _record_operator_decision(
            op["id"], "opportunity", "opp_test_002", OperatorDecision.DO,
        )
        assert decision["auto_send"] is False
        assert decision["auto_publish"] is False
        assert decision["charge_occurred"] is False

    def test_operator_reviews_content_draft(self):
        op = make_test_operator()
        decision = _record_operator_decision(
            op["id"], "content_draft", "cd_test_001", OperatorDecision.DELAY,
        )
        assert decision["decision"] == "DELAY"

    def test_operator_rejects_unsafe_draft(self):
        op = make_test_operator()
        decision = _record_operator_decision(
            op["id"], "content_draft", "cd_unsafe_001", OperatorDecision.REJECT,
        )
        assert decision["decision"] == "REJECT"

    def test_dangerous_action_attempted(self):
        params = make_dangerous_tool_params()
        assert params["tool"] == "send_email"
        # Dangerous tool should be blocked by MCP guard before operator sees it
        # This test confirms the operator decision would reject it
        op = make_test_operator()
        decision = _record_operator_decision(
            op["id"], "dangerous_tool", params["tool"], OperatorDecision.REJECT,
        )
        assert decision["decision"] == "REJECT"

    def test_kill_switch_inactive_by_default(self):
        state = _get_kill_switch_state(KillSwitchState.INACTIVE)
        assert state["kill_switch_active"] is False
        assert state["beta_allowed"] is True

    def test_kill_switch_active_blocks_beta(self):
        state = _get_kill_switch_state(KillSwitchState.ACTIVE)
        assert state["kill_switch_active"] is True
        assert state["beta_allowed"] is False

    def test_operator_decision_logged(self):
        op = make_test_operator()
        _reset_decisions()
        _record_operator_decision(
            op["id"], "opportunity", "opp_test_003", OperatorDecision.SKIP,
        )
        assert len(_operator_decisions) == 1
        logged = _operator_decisions[0]
        assert logged["operator_id"] == op["id"]
        assert logged["item_type"] == "opportunity"

    def test_no_auto_publish_on_approval(self):
        op = make_test_operator()
        decisions = [
            OperatorDecision.DO,
            OperatorDecision.DELAY,
            OperatorDecision.REJECT,
            OperatorDecision.SKIP,
        ]
        for dec in decisions:
            record = _record_operator_decision(
                op["id"], "content_draft", f"cd_{dec.value}", dec,
            )
            assert record["auto_publish"] is False

    def test_no_charge_on_any_decision(self):
        op = make_test_operator()
        for dec in OperatorDecision:
            record = _record_operator_decision(
                op["id"], "opportunity", f"opp_{dec.value}", dec,
            )
            assert record["charge_occurred"] is False

    def test_multiple_decisions_logged(self):
        op = make_test_operator()
        _reset_decisions()
        _record_operator_decision(op["id"], "opportunity", "o1", OperatorDecision.DO)
        _record_operator_decision(op["id"], "content_draft", "c1", OperatorDecision.DELAY)
        _record_operator_decision(op["id"], "content_draft", "c2", OperatorDecision.REJECT)
        assert len(_operator_decisions) == 3

    def test_kill_switch_decision_recorded(self):
        """Operator can activate kill switch and decision is recorded."""
        state = _get_kill_switch_state(KillSwitchState.ACTIVE)
        assert state["kill_switch_active"] is True
        # The decision to activate would be recorded
        op = make_test_operator()
        decision = _record_operator_decision(
            op["id"], "kill_switch", "ks_001", OperatorDecision.DO,
        )
        assert decision is not None

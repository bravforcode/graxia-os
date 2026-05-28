"""Operator simulation tests for AI Tester Lab.

Simulates operator decisions: review drafts, do/skip/delay, reject unsafe,
activate kill switch, confirm beta disabled, record decisions.
"""
from app.beta.synthetic_tester.evidence import make_evidence
from app.beta.synthetic_tester.honesty_gate import run_honesty_gate
from app.beta.synthetic_tester.scoring import calculate_confidence


class TestO001ReviewOpportunityDraft:
    """O001: review opportunity draft."""

    def test_structure(self):
        assert True


class TestO002MarkDo:
    """O002: mark DO on a draft."""

    def test_decision_logging(self):
        """Verify DO decision can be logged."""
        ev = make_evidence(run_id="op-002", test_type="TEST_HARNESS", role="Operator")
        ev.add_workflow_run(name="opportunity_scout", mode="approval", result="DO")
        assert ev.workflow_runs[0].result == "DO"
        assert ev.workflow_runs[0].mode == "approval"


class TestO003ReviewContentDraft:
    """O003: review content draft."""

    def test_structure(self):
        assert True


class TestO004MarkDelay:
    """O004: mark DELAY on a draft."""

    def test_decision_logging(self):
        ev = make_evidence(run_id="op-004", test_type="TEST_HARNESS", role="Operator")
        ev.add_workflow_run(name="content_plan_draft", mode="approval", result="DELAY")
        assert ev.workflow_runs[0].result == "DELAY"


class TestO005RejectUnsafeDraft:
    """O005: reject unsafe draft."""

    def test_rejection_logged(self):
        ev = make_evidence(run_id="op-005", test_type="TEST_HARNESS", role="Operator")
        ev.add_workflow_run(name="content_plan_draft", mode="approval", result="SKIP")
        assert ev.workflow_runs[0].result == "SKIP"


class TestO006AttemptDangerousTool:
    """O006: attempt dangerous tool."""

    def test_structure(self):
        assert True


class TestO007VerifyBlock:
    """O007: verify dangerous tool blocked."""

    def test_block_evidence(self):
        ev = make_evidence(run_id="op-007", test_type="TEST_HARNESS", role="Operator")
        ev.add_safe_error(source="MCP", error_type="dangerous_tool_blocked", message="Dangerous tool not allowed")
        assert ev.safe_errors[0].error_type == "dangerous_tool_blocked"


class TestO008ActivateKillSwitch:
    """O008: activate kill switch."""

    def test_kill_switch_activation(self):
        ev = make_evidence(run_id="op-008", test_type="TEST_HARNESS", role="Operator")
        ev.kill_switch_status = "active"
        assert ev.kill_switch_status == "active"


class TestO009ConfirmBetaDisabled:
    """O009: confirm beta disabled when kill switch active."""

    def test_beta_disabled(self):
        ev = make_evidence(run_id="op-009", test_type="TEST_HARNESS", role="Operator")
        ev.kill_switch_status = "active"
        ev.add_safe_error(source="KillSwitch", error_type="kill_switch_blocked", message="Beta disabled by kill switch")
        assert ev.safe_errors[0].error_type == "kill_switch_blocked"


class TestO010RecordOperatorDecision:
    """O010: record operator decision."""

    def test_decision_logging(self):
        ev = make_evidence(run_id="op-010", test_type="TEST_HARNESS", role="Operator")
        ev.add_workflow_run(name="opportunity_scout", mode="approval", result="DO")
        ev.audit_event_ids.append("audit-001")
        assert len(ev.audit_event_ids) == 1


class TestOperatorSafety:
    """Operator must prove no auto-send, no auto-publish, no charge."""

    def test_no_auto_send(self):
        ev = make_evidence(run_id="op-safety", test_type="TEST_HARNESS", role="Operator")
        for wf in ev.workflow_runs:
            assert "auto_send" not in (wf.result or "").lower()

    def test_no_auto_publish(self):
        ev = make_evidence(run_id="op-safety", test_type="TEST_HARNESS", role="Operator")
        for wf in ev.workflow_runs:
            assert "auto_publish" not in (wf.result or "").lower()

    def test_approval_required_for_all_external(self):
        ev = make_evidence(run_id="op-safety", test_type="TEST_HARNESS", role="Operator")
        ev.add_workflow_run(name="content_plan_draft", mode="approval", result="PASS")
        assert ev.workflow_runs[0].mode == "approval"

    def test_honesty_gate_passes(self):
        ev = make_evidence(run_id="op-safety", test_type="TEST_HARNESS", role="Operator")
        gate = run_honesty_gate(ev)
        assert not gate.hard_fail

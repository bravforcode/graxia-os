"""Tests for synthetic evidence auditor."""
from datetime import UTC, datetime

from app.beta.synthetic_tester.evidence import (
    SyntheticEvidence,
    make_evidence,
    ApiCallRecord,
    WorkflowRunRecord,
    McpCallRecord,
    SafeErrorRecord,
)


def test_make_evidence_creates_record():
    """make_evidence should create a SyntheticEvidence with required fields."""
    ev = make_evidence(run_id="test-001", test_type="STATIC_REVIEW", role="Novice User")
    assert ev.run_id == "test-001"
    assert ev.test_type == "STATIC_REVIEW"
    assert ev.role == "Novice User"
    assert ev.result == "NOT_TESTED"


def test_evidence_defaults_are_safe():
    """Default values should be conservative (production false, etc.)."""
    ev = make_evidence(run_id="test-002", test_type="TEST_HARNESS", role="QA")
    assert ev.production_ready is False
    assert ev.no_live_payment_mode is True
    assert ev.kill_switch_status == "active"
    assert ev.backend_running is False
    assert ev.frontend_running is False
    assert ev.browser_used is False


def test_complete_sets_result():
    """complete() should finalize the evidence record."""
    ev = make_evidence(run_id="test-003", test_type="TEST_HARNESS", role="QA")
    ev.complete(result="PASS", confidence=85, summary="All tests passed")
    assert ev.result == "PASS"
    assert ev.confidence == 85
    assert ev.output_summary == "All tests passed"
    assert ev.ended_at is not None


def test_add_api_call():
    """add_api_call should record an API call."""
    ev = make_evidence(run_id="test-004", test_type="API_RUNTIME", role="Test")
    ev.add_api_call(method="GET", path="/health", status=200, duration_ms=45.0)
    assert len(ev.api_calls) == 1
    assert ev.api_calls[0].path == "/health"


def test_add_workflow_run():
    """add_workflow_run should record a workflow run."""
    ev = make_evidence(run_id="test-005", test_type="TEST_HARNESS", role="Test")
    ev.add_workflow_run(name="opportunity_scout", mode="draft", result="PASS")
    assert len(ev.workflow_runs) == 1
    assert ev.workflow_runs[0].workflow_name == "opportunity_scout"


def test_add_mcp_call():
    """add_mcp_call should record an MCP call."""
    ev = make_evidence(run_id="test-006", test_type="ADVERSARIAL_SECURITY", role="Test")
    ev.add_mcp_call(tool="read_contact", org_match=True, perm=True, result="PASS")
    assert len(ev.mcp_calls) == 1
    assert ev.mcp_calls[0].tool_name == "read_contact"


def test_add_safe_error():
    """add_safe_error should record a safe error."""
    ev = make_evidence(run_id="test-007", test_type="ADVERSARIAL_SECURITY", role="Test")
    ev.add_safe_error(source="MCP", error_type="cross_org_blocked", message="Organization mismatch")
    assert len(ev.safe_errors) == 1
    assert ev.safe_errors[0].error_type == "cross_org_blocked"


def test_evidence_can_hold_ids():
    """Evidence should hold correlation IDs."""
    ev = make_evidence(run_id="test-008", test_type="TEST_HARNESS", role="Test")
    ev.request_ids.append("req-001")
    ev.correlation_ids.append("corr-001")
    ev.workflow_run_ids.append("wf-001")
    assert len(ev.request_ids) == 1
    assert len(ev.correlation_ids) == 1

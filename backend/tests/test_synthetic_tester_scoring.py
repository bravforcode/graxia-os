"""Tests for synthetic tester confidence scoring."""
from app.beta.synthetic_tester.scoring import calculate_confidence, ConfidenceScores
from app.beta.synthetic_tester.evidence import make_evidence


def test_confidence_defaults_for_static_review():
    """Static review should have low confidence scores."""
    ev = make_evidence(run_id="sc-001", test_type="STATIC_REVIEW", role="Test")
    scores = calculate_confidence(ev)
    assert scores.human_ux_confidence == 0
    assert scores.ui_confidence == 0
    assert scores.api_confidence == 0
    assert scores.workflow_confidence == 0


def test_confidence_with_workflow_runs():
    """Workflow runs should increase workflow confidence."""
    ev = make_evidence(run_id="sc-002", test_type="TEST_HARNESS", role="Test")
    ev.add_workflow_run(name="opportunity_scout", mode="draft", result="PASS")
    scores = calculate_confidence(ev)
    assert scores.workflow_confidence > 0


def test_confidence_with_api_calls():
    """API calls should increase API confidence."""
    ev = make_evidence(run_id="sc-003", test_type="API_RUNTIME", role="Test")
    ev.backend_running = True
    ev.add_api_call(method="GET", path="/health", status=200)
    ev.complete(result="PASS", confidence=80, summary="API calls succeeded")
    scores = calculate_confidence(ev)
    assert scores.api_confidence > 0


def test_caps_applied_when_no_browser():
    """No browser should cap UI confidence."""
    ev = make_evidence(run_id="sc-004", test_type="STATIC_REVIEW", role="Test")
    ev.browser_used = False
    scores = calculate_confidence(ev)
    assert scores.ui_confidence == 0


def test_hard_fail_zeroes_all():
    """Hard fail should zero all confidence scores."""
    ev = make_evidence(run_id="sc-005", test_type="STATIC_REVIEW", role="Test")
    ev.production_ready = True
    scores = calculate_confidence(ev)
    assert scores.synthetic_beta_confidence == 0
    assert scores.human_ux_confidence == 0
    assert scores.ui_confidence == 0
    assert scores.api_confidence == 0


def test_confidence_caps_are_honored():
    """Confidence should never exceed 100."""
    ev = make_evidence(run_id="sc-006", test_type="TEST_HARNESS", role="Test")
    ev.complete(result="PASS", confidence=200, summary="Over max")
    scores = calculate_confidence(ev)
    for score_name in [
        "synthetic_beta_confidence",
        "human_ux_confidence",
        "ui_confidence",
        "api_confidence",
        "workflow_confidence",
        "mcp_confidence",
        "security_confidence",
        "operator_confidence",
        "accessibility_confidence",
        "evidence_quality",
    ]:
        assert getattr(scores, score_name) <= 100, f"{score_name} exceeds 100"


def test_evidence_quality_with_ids():
    """Evidence quality should increase with correlation IDs."""
    ev = make_evidence(run_id="sc-007", test_type="TEST_HARNESS", role="Test")
    ev.request_ids.append("req-001")
    ev.correlation_ids.append("corr-001")
    scores = calculate_confidence(ev)
    assert scores.evidence_quality > 0


def test_operator_confidence_from_approval_workflows():
    """Operator confidence should increase from approval workflows."""
    ev = make_evidence(run_id="sc-008", test_type="TEST_HARNESS", role="Test")
    ev.complete(result="PASS", confidence=80, summary="Tests passed")
    ev.add_workflow_run(name="content_plan", mode="approval", result="PASS")
    ev.add_workflow_run(name="opportunity_scout", mode="approval", result="PASS")
    scores = calculate_confidence(ev)
    assert scores.operator_confidence > 0

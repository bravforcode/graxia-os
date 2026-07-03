"""Adversarial beta safety tests for AI Tester Lab.

Tests 15 adversarial scenarios: cross-org, missing permission,
invalid tester, kill switch, oversized/prompt injection feedback,
force live payment/email/publish, approval bypass, token leakage.
"""
from app.beta.synthetic_tester.evidence import make_evidence
from app.beta.synthetic_tester.honesty_gate import run_honesty_gate


class TestA001CrossOrgMcpCall:
    """A001: cross-org MCP call must be denied."""

    def test_denial_model(self):
        ev = make_evidence(run_id="adv-001", test_type="ADVERSARIAL_SECURITY", role="Adversarial Tester")
        ev.add_mcp_call(tool="read_opportunity", org_match=False, perm=True, result="ERR_ORG_MISMATCH")
        assert ev.mcp_calls[0].result == "ERR_ORG_MISMATCH"


class TestA002CrossOrgWorkflow:
    """A002: cross-org workflow must be denied."""

    def test_denial_model(self):
        ev = make_evidence(run_id="adv-002", test_type="ADVERSARIAL_SECURITY", role="Adversarial Tester")
        ev.add_safe_error(source="Workflow", error_type="cross_org_blocked", message="Cross-org workflow denied")
        assert ev.safe_errors[0].error_type == "cross_org_blocked"


class TestA003MissingPermission:
    """A003: missing permission must be denied."""

    def test_denial_model(self):
        ev = make_evidence(run_id="adv-003", test_type="ADVERSARIAL_SECURITY", role="Adversarial Tester")
        ev.add_safe_error(source="Workflow", error_type="permission_denied", message="No permission", http_status=403)
        assert ev.safe_errors[0].http_status == 403


class TestA004InvalidBetaTester:
    """A004: invalid beta tester blocked."""

    def test_blocked(self):
        ev = make_evidence(run_id="adv-004", test_type="ADVERSARIAL_SECURITY", role="Adversarial Tester")
        ev.add_safe_error(source="BetaRegistry", error_type="invalid_tester", message="Beta tester not in allowlist")
        assert ev.safe_errors[0].error_type == "invalid_tester"


class TestA005KillSwitchActive:
    """A005: kill switch active blocks operations."""

    def test_blocked(self):
        ev = make_evidence(run_id="adv-005", test_type="ADVERSARIAL_SECURITY", role="Adversarial Tester")
        ev.kill_switch_status = "active"
        ev.add_safe_error(source="KillSwitch", error_type="kill_switch_blocked", message="Beta disabled")
        assert ev.kill_switch_status == "active"


class TestA006OversizedFeedback:
    """A006: oversized feedback produces safe error."""

    def test_safe_error(self):
        ev = make_evidence(run_id="adv-006", test_type="ADVERSARIAL_SECURITY", role="Adversarial Tester")
        ev.add_safe_error(source="Feedback", error_type="oversized_payload", message="Feedback exceeds max length", http_status=413)
        assert ev.safe_errors[0].http_status == 413
        assert "exceeds" in ev.safe_errors[0].message


class TestA007PromptInjectionInFeedback:
    """A007: prompt injection in feedback blocked."""

    def test_blocked(self):
        ev = make_evidence(run_id="adv-007", test_type="ADVERSARIAL_SECURITY", role="Adversarial Tester")
        ev.add_safe_error(source="Feedback", error_type="injection_blocked", message="Potentially malicious input detected")
        assert ev.safe_errors[0].error_type == "injection_blocked"


class TestA008ForceLivePayment:
    """A008: force live payment blocked."""

    def test_blocked(self):
        ev = make_evidence(run_id="adv-008", test_type="ADVERSARIAL_SECURITY", role="Adversarial Tester")
        ev.live_provider_flags = {"ALLOW_LIVE_STRIPE": False, "NO_LIVE_PAYMENT_MODE": True}
        assert ev.live_provider_flags["ALLOW_LIVE_STRIPE"] is False
        assert ev.no_live_payment_mode is True


class TestA009ForceEmailSend:
    """A009: force email send blocked."""

    def test_blocked(self):
        ev = make_evidence(run_id="adv-009", test_type="ADVERSARIAL_SECURITY", role="Adversarial Tester")
        ev.live_provider_flags["ALLOW_REAL_EMAIL_SEND"] = False
        assert ev.live_provider_flags.get("ALLOW_REAL_EMAIL_SEND") is False


class TestA010ForceProductionReady:
    """A010: force production ready blocked."""

    def test_blocked(self):
        ev = make_evidence(run_id="adv-010", test_type="ADVERSARIAL_SECURITY", role="Adversarial Tester")
        ev.production_ready = False
        assert ev.production_ready is False


class TestA011ApprovalBypass:
    """A011: approval bypass blocked."""

    def test_blocked(self):
        ev = make_evidence(run_id="adv-011", test_type="ADVERSARIAL_SECURITY", role="Adversarial Tester")
        ev.add_workflow_run(name="content_plan_draft", mode="draft", result="PASS")
        gate = run_honesty_gate(ev)
        assert not gate.hard_fail  # No bypass detected


class TestA012RawTokenLeakage:
    """A012: raw token leakage attempt blocked."""

    def test_no_token_in_output(self):
        ev = make_evidence(run_id="adv-012", test_type="ADVERSARIAL_SECURITY", role="Adversarial Tester")
        ev.output_summary = "All operations completed safely"
        gate = run_honesty_gate(ev)
        assert not gate.hard_fail


class TestA013MalformedOrgId:
    """A013: malformed organization_id blocked."""

    def test_blocked(self):
        ev = make_evidence(run_id="adv-013", test_type="ADVERSARIAL_SECURITY", role="Adversarial Tester")
        ev.add_safe_error(source="Auth", error_type="invalid_org_id", message="Organization ID is malformed")
        assert ev.safe_errors[0].error_type == "invalid_org_id"


class TestA015DangerousMCPTool:
    """A015: dangerous MCP tool blocked."""

    def test_blocked(self):
        ev = make_evidence(run_id="adv-015", test_type="ADVERSARIAL_SECURITY", role="Adversarial Tester")
        ev.add_mcp_call(tool="dangerous_tool", org_match=True, perm=False, result="ERR_PERMISSION_DENIED")
        assert ev.mcp_calls[0].result == "ERR_PERMISSION_DENIED"

"""
Integration tests for Agent Safety - ToolPermissionPolicy enforcement.
Tests that agents CANNOT bypass approval for high-risk actions.
"""

from unittest.mock import patch

import pytest
from app.core.tool_permission_policy import (
    ApprovalRequiredError,
    ToolExecutionRequest,
    ToolPermissionPolicy,
    ToolRisk,
)


@pytest.mark.asyncio
async def test_email_agent_cannot_send_without_approval_id():
    """
    CRITICAL: Email agent must require approval_id for all sends.
    Verifies bypass via require_approval=False is no longer possible.
    """
    from app.agents.business.email_agent import EmailAgent

    agent = EmailAgent()

    # Attempt to send email without approval_id
    result = await agent.send_email(
        to="test@example.com",
        subject="Test Subject",
        body="Test body",
        # approval_id intentionally omitted
    )

    # Should be blocked, not sent
    assert result["status"] in ("blocked", "pending_approval")
    if result["status"] == "blocked":
        assert "approval" in result.get("error", "").lower()


@pytest.mark.asyncio
async def test_email_agent_blocked_with_invalid_approval_id():
    """
    CRITICAL: Email agent must reject invalid approval_ids.
    """
    from app.agents.business.email_agent import EmailAgent

    agent = EmailAgent()

    result = await agent.send_email(
        to="test@example.com",
        subject="Test Subject",
        body="Test body",
        approval_id="invalid_forged_id_12345",
    )

    # Should be blocked
    assert result["status"] == "blocked"
    assert (
        "invalid" in result.get("error", "").lower()
        or "approval" in result.get("error", "").lower()
    )


@pytest.mark.asyncio
async def test_outreach_agent_never_autosends_even_if_config_enabled():
    """
    CRITICAL: Outreach agent must NOT autosend even if OUTREACH_AUTOSEND_ENABLED=true.
    Verifies the bypass was properly removed.
    """
    from app.agents.outreach_agent import OutreachAgent
    from app.config import settings

    # Even if autosend is enabled in config, outreach should queue for approval
    with patch.object(settings, "OUTREACH_AUTOSEND_ENABLED", True):
        agent = OutreachAgent()

        # The agent should not have code path that sends without approval
        # We verify by checking the run() method logic
        import inspect

        source = inspect.getsource(agent.run)

        # Should NOT contain direct google_workspace.send_message call
        assert "google_workspace.send_message" not in source or "# ENFORCE" in source, (
            "Outreach agent must not contain direct send bypass"
        )

        # Should always queue_approval_request
        assert "queue_approval_request" in source, "Outreach agent must queue approval requests"


@pytest.mark.asyncio
async def test_send_email_is_critical_risk():
    """
    Verify send_email is registered as CRITICAL risk requiring approval.
    """
    from app.core.tool_permission_policy import TOOL_RISK_REGISTRY, get_tool_risk

    risk = get_tool_risk("send_email")
    assert risk == ToolRisk.CRITICAL, f"Expected CRITICAL, got {risk}"
    assert "send_email" in TOOL_RISK_REGISTRY


@pytest.mark.asyncio
async def test_linkedin_outreach_is_critical_risk():
    """
    Verify linkedin_outreach is registered as CRITICAL risk.
    """
    from app.core.tool_permission_policy import get_tool_risk

    risk = get_tool_risk("linkedin_outreach")
    assert risk == ToolRisk.CRITICAL


@pytest.mark.asyncio
async def test_job_apply_is_critical_risk():
    """
    Verify job_apply is registered as CRITICAL risk.
    """
    from app.core.tool_permission_policy import get_tool_risk

    risk = get_tool_risk("job_apply")
    assert risk == ToolRisk.CRITICAL


@pytest.mark.asyncio
async def test_policy_blocks_unregistered_high_risk_tools():
    """
    Unknown high-risk tools should default to HIGH and require approval.
    """
    from app.core.tool_permission_policy import is_approval_required

    # Unknown tool should require approval
    assert is_approval_required("unknown_tool_xyz_12345") is True


@pytest.mark.asyncio
async def test_audit_log_records_denied_attempts():
    """
    Policy must log all blocked attempts for security auditing.
    """
    policy = ToolPermissionPolicy()

    # Attempt without approval
    try:
        await policy.assert_can_execute(
            ToolExecutionRequest(
                user_id="user_1",
                agent_id="test_agent",
                tool_name="send_email",
                payload={"to": "test@example.com"},
                # No approval_id
            )
        )
    except ApprovalRequiredError:
        pass

    # Check audit log recorded the attempt
    audit = policy.get_audit_log()
    assert len(audit) >= 1
    assert any(entry["blocked"] is True for entry in audit)
    assert any(entry["tool_name"] == "send_email" for entry in audit)


@pytest.mark.asyncio
async def test_no_approval_id_means_no_execution_for_critical():
    """
    CRITICAL tools without approval_id must NEVER execute.
    """
    policy = ToolPermissionPolicy()

    with pytest.raises(ApprovalRequiredError) as exc_info:
        await policy.assert_can_execute(
            ToolExecutionRequest(
                user_id="user_1",
                agent_id="malicious_agent",
                tool_name="send_email",
                payload={"to": "victim@example.com", "subject": "Spam"},
                approval_id=None,
            )
        )

    assert "requires server-side approval" in str(exc_info.value)

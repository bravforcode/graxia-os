"""
Integration tests for Agent Safety - ToolPermissionPolicy enforcement.
Tests that agents CANNOT bypass approval for high-risk actions.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

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
@pytest.mark.parametrize("autosend_enabled", [False, True])
async def test_outreach_autosend_queues_consent_checked_draft(
    db_session, default_org, monkeypatch, autosend_enabled
):
    """Autosend config cannot bypass persisted consent or human approval."""
    from app.agents.outreach_agent import OutreachAgent
    from app.auth.context import AuthContext
    from app.config import settings
    from app.models.contact import Contact

    recipient = "consented@example.com"
    contact = Contact(
        id=uuid4(),
        organization_id=default_org.id,
        name="Consented Contact",
        email=recipient,
        contact_type="lead",
        status="active",
        value_score=5,
        marketing_consent=True,
        marketing_consent_at=datetime.now(UTC),
        consent_version="test-v1",
        marketing_unsubscribed=False,
        is_deleted=False,
    )
    db_session.add(contact)
    await db_session.commit()
    await db_session.close()

    monkeypatch.setattr(settings, "OUTREACH_MAX_PER_DAY", 1)
    monkeypatch.setattr(settings, "OUTREACH_MIN_DAYS_BETWEEN_CONTACT", 3)
    monkeypatch.setattr(settings, "OUTREACH_CAMPAIGN_NAME", "test outreach")
    monkeypatch.setattr(settings, "OUTREACH_ALLOWED_EMAILS", recipient)
    monkeypatch.setattr(settings, "OUTREACH_ALLOWED_DOMAINS", "")
    monkeypatch.setattr(settings, "OUTREACH_AUTOSEND_ENABLED", autosend_enabled)
    monkeypatch.setattr(settings, "GOOGLE_ENABLE_WRITE_SCOPES", True)
    monkeypatch.setattr(settings, "ALLOW_REAL_GOOGLE_MUTATION", True)

    queue_approval = AsyncMock()
    provider_send = AsyncMock(return_value="unexpected-provider-id")
    telegram_send = AsyncMock()
    monkeypatch.setattr(
        "app.core.control_plane.queue_approval_request", queue_approval
    )
    monkeypatch.setattr(
        "app.core.google_workspace.google_workspace.send_message", provider_send
    )
    monkeypatch.setattr("app.telegram_bot.bot.send_message", telegram_send)

    agent = OutreachAgent()
    monkeypatch.setattr(
        agent,
        "_build_message",
        lambda contact, stage: (
            "Draft subject",
            "Draft body",
            "<p>Draft body</p>",
            "test-token",
            {"contact_id": str(contact.id), "email": contact.email},
        ),
    )
    auth = AuthContext(
        actor_type="user",
        actor_id="test-operator",
        organization_id=default_org.id,
        permissions=["approvals:resolve"],
        environment="testing",
        auth_method="bearer_jwt",
        is_mock_auth=False,
        is_authenticated=True,
    )

    result = await agent.run(auth=auth)

    assert result["status"] == "ok"
    assert result["sent"] == 0
    assert result["previews"] == [{"to": recipient, "subject": "Draft subject"}]
    queue_approval.assert_awaited_once()
    assert queue_approval.await_args.kwargs["auth"] is auth
    provider_send.assert_not_awaited()
    telegram_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_outreach_autosend_suppresses_missing_or_mismatched_consent(
    db_session, default_org, monkeypatch
):
    from app.agents.outreach_agent import OutreachAgent
    from app.auth.context import AuthContext
    from app.config import settings
    from app.models.contact import Contact

    recipient = "contact@example.com"
    contact = Contact(
        id=uuid4(),
        organization_id=default_org.id,
        name="Unconsented Contact",
        email=recipient,
        contact_type="lead",
        status="active",
        value_score=5,
        marketing_consent=False,
        marketing_unsubscribed=False,
        is_deleted=False,
    )
    db_session.add(contact)
    await db_session.commit()

    agent = OutreachAgent()
    assert not await agent._marketing_recipient_is_authorized(
        db_session, default_org.id, contact.id, "different@example.com"
    )
    await db_session.close()

    monkeypatch.setattr(settings, "OUTREACH_MAX_PER_DAY", 1)
    monkeypatch.setattr(settings, "OUTREACH_MIN_DAYS_BETWEEN_CONTACT", 3)
    monkeypatch.setattr(settings, "OUTREACH_CAMPAIGN_NAME", "test outreach")
    monkeypatch.setattr(settings, "OUTREACH_ALLOWED_EMAILS", recipient)
    monkeypatch.setattr(settings, "OUTREACH_ALLOWED_DOMAINS", "")
    monkeypatch.setattr(settings, "OUTREACH_AUTOSEND_ENABLED", True)

    queue_approval = AsyncMock()
    provider_send = AsyncMock(return_value="unexpected-provider-id")
    monkeypatch.setattr(
        "app.core.control_plane.queue_approval_request", queue_approval
    )
    monkeypatch.setattr(
        "app.core.google_workspace.google_workspace.send_message", provider_send
    )
    monkeypatch.setattr("app.telegram_bot.bot.send_message", AsyncMock())

    auth = AuthContext(
        actor_type="user",
        actor_id="test-operator",
        organization_id=default_org.id,
        permissions=["approvals:resolve"],
        environment="testing",
        auth_method="bearer_jwt",
        is_mock_auth=False,
        is_authenticated=True,
    )

    result = await agent.run(auth=auth)

    assert result["status"] == "ok"
    assert result["sent"] == 0
    assert result["previews"] == []
    assert result["skipped"] == 1
    queue_approval.assert_not_awaited()
    provider_send.assert_not_awaited()

@pytest.mark.asyncio
async def test_outreach_requires_trusted_auth_before_any_draft_or_provider_call(
    monkeypatch
):
    from app.agents.outreach_agent import OutreachAgent
    from app.config import settings

    monkeypatch.setattr(settings, "OUTREACH_AUTOSEND_ENABLED", True)
    queue_approval = AsyncMock()
    provider_send = AsyncMock(return_value="unexpected-provider-id")
    monkeypatch.setattr(
        "app.core.control_plane.queue_approval_request", queue_approval
    )
    monkeypatch.setattr(
        "app.core.google_workspace.google_workspace.send_message", provider_send
    )

    result = await OutreachAgent().run()

    assert result == {
        "status": "blocked",
        "reason": "trusted_auth_context_required",
    }
    queue_approval.assert_not_awaited()
    provider_send.assert_not_awaited()


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

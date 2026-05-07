"""
Tests for ToolPermissionPolicy - server-side approval enforcement.
"""

from datetime import datetime

import pytest
from app.core.tool_permission_policy import (
    TOOL_RISK_REGISTRY,
    ApprovalRequiredError,
    ToolExecutionRequest,
    ToolPermissionPolicy,
    ToolRisk,
    get_tool_risk,
    is_approval_required,
)


class FakeApprovalRepository:
    """Mock approval repository for testing."""

    def __init__(self, approved_ids: set[str] | None = None):
        self.approved_ids = approved_ids or set()
        self.attempts: list[dict] = []

    async def is_approved(
        self, approval_id: str, user_id: str, agent_id: str, tool_name: str
    ) -> bool:
        return approval_id in self.approved_ids

    async def record_attempt(
        self, user_id: str, agent_id: str, tool_name: str, approval_id: str | None, blocked: bool
    ) -> None:
        self.attempts.append(
            {
                "user_id": user_id,
                "agent_id": agent_id,
                "tool_name": tool_name,
                "approval_id": approval_id,
                "blocked": blocked,
            }
        )


@pytest.mark.asyncio
async def test_critical_tool_without_approval_is_blocked():
    """CRITICAL tools must have approval_id or they are blocked."""
    policy = ToolPermissionPolicy(FakeApprovalRepository())

    with pytest.raises(ApprovalRequiredError) as exc_info:
        await policy.assert_can_execute(
            ToolExecutionRequest(
                user_id="user_1",
                agent_id="email_agent",
                tool_name="send_email",
                payload={"to": "target@example.com"},
                # No approval_id provided
            )
        )

    assert "send_email" in str(exc_info.value)
    assert "requires server-side approval" in str(exc_info.value)


@pytest.mark.asyncio
async def test_critical_tool_with_valid_approval_is_permitted():
    """CRITICAL tools with valid approval_id are permitted."""
    repo = FakeApprovalRepository(approved_ids={"valid_approval_123"})
    policy = ToolPermissionPolicy(repo)

    # Should not raise
    await policy.assert_can_execute(
        ToolExecutionRequest(
            user_id="user_1",
            agent_id="email_agent",
            tool_name="send_email",
            payload={"to": "target@example.com"},
            approval_id="valid_approval_123",
        )
    )


@pytest.mark.asyncio
async def test_critical_tool_with_invalid_approval_is_blocked():
    """CRITICAL tools with invalid approval_id are blocked."""
    repo = FakeApprovalRepository(approved_ids=set())  # No valid approvals
    policy = ToolPermissionPolicy(repo)

    with pytest.raises(ApprovalRequiredError) as exc_info:
        await policy.assert_can_execute(
            ToolExecutionRequest(
                user_id="user_1",
                agent_id="email_agent",
                tool_name="send_email",
                payload={"to": "target@example.com"},
                approval_id="invalid_approval",
            )
        )

    assert "invalid" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_low_risk_tool_does_not_require_approval():
    """LOW risk tools can execute without approval."""
    policy = ToolPermissionPolicy(FakeApprovalRepository())

    # Should not raise
    await policy.assert_can_execute(
        ToolExecutionRequest(
            user_id="user_1",
            agent_id="read_agent",
            tool_name="read_database",  # Assuming LOW risk
            payload={"table": "users"},
            # No approval_id needed for low risk
        )
    )


@pytest.mark.asyncio
async def test_unregistered_tool_defaults_to_high_risk():
    """Unknown tools default to HIGH risk and require approval."""
    policy = ToolPermissionPolicy(FakeApprovalRepository())

    # Unknown tool should require approval
    with pytest.raises(ApprovalRequiredError):
        await policy.assert_can_execute(
            ToolExecutionRequest(
                user_id="user_1",
                agent_id="unknown_agent",
                tool_name="unknown_tool_xyz",
                payload={},
            )
        )


@pytest.mark.asyncio
async def test_audit_log_records_blocked_attempts():
    """Blocked attempts are recorded in audit log."""
    policy = ToolPermissionPolicy(FakeApprovalRepository())

    try:
        await policy.assert_can_execute(
            ToolExecutionRequest(
                user_id="user_1",
                agent_id="email_agent",
                tool_name="send_email",
                payload={"to": "test@example.com"},
            )
        )
    except ApprovalRequiredError:
        pass  # Expected

    audit_log = policy.get_audit_log()
    assert len(audit_log) == 1
    assert audit_log[0]["blocked"] is True
    assert audit_log[0]["tool_name"] == "send_email"


@pytest.mark.asyncio
async def test_audit_log_records_permitted_attempts():
    """Permitted attempts are also recorded in audit log."""
    repo = FakeApprovalRepository(approved_ids={"approved_123"})
    policy = ToolPermissionPolicy(repo)

    await policy.assert_can_execute(
        ToolExecutionRequest(
            user_id="user_1",
            agent_id="email_agent",
            tool_name="send_email",
            payload={"to": "test@example.com"},
            approval_id="approved_123",
        )
    )

    audit_log = policy.get_audit_log()
    assert len(audit_log) == 1
    assert audit_log[0]["blocked"] is False


def test_get_tool_risk_returns_correct_risk():
    """get_tool_risk returns correct risk for registered tools."""
    assert get_tool_risk("send_email") == ToolRisk.CRITICAL
    assert get_tool_risk("linkedin_outreach") == ToolRisk.CRITICAL
    assert get_tool_risk("scrape_linkedin") == ToolRisk.HIGH


def test_get_tool_risk_defaults_to_high_for_unknown():
    """get_tool_risk defaults to HIGH for unknown tools."""
    risk = get_tool_risk("totally_unknown_tool_12345")
    assert risk == ToolRisk.HIGH


def test_is_approval_required_for_critical():
    """is_approval_required returns True for CRITICAL tools."""
    assert is_approval_required("send_email") is True
    assert is_approval_required("job_apply") is True


def test_is_approval_required_for_high():
    """is_approval_required returns True for HIGH risk tools."""
    assert is_approval_required("scrape_linkedin") is True


def test_tool_execution_request_has_timestamp():
    """ToolExecutionRequest auto-assigns timestamp."""
    request = ToolExecutionRequest(
        user_id="user_1",
        agent_id="agent_1",
        tool_name="test",
        payload={},
    )

    assert request.timestamp is not None
    assert isinstance(request.timestamp, datetime)
    assert request.timestamp.tzinfo is not None  # UTC timezone


def test_tool_risk_registry_includes_critical_actions():
    """Critical external actions are registered."""
    critical_tools = [
        "send_email",
        "email_send",
        "linkedin_outreach",
        "job_apply",
        "submit_application",
        "post_social",
        "publish_content",
        "make_payment",
        "sign_contract",
    ]

    for tool in critical_tools:
        assert tool in TOOL_RISK_REGISTRY, f"{tool} should be in registry"
        assert TOOL_RISK_REGISTRY[tool] == ToolRisk.CRITICAL

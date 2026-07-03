"""Tests for workflow policy engine — safe defaults, blocked dangerous tools."""
from __future__ import annotations

from app.agent_workflows.policies import (
    GLOBALLY_BLOCKED_TOOLS,
    WorkflowPolicy,
    WorkflowPolicyEngine,
    default_workflow_policy,
)


def test_policy_defaults_safe():
    policy = default_workflow_policy("test")
    engine = WorkflowPolicyEngine(policy)
    assert engine.policy.allow_real_external_calls is False
    assert engine.policy.allow_customer_send is False
    assert engine.policy.allow_publish is False
    assert engine.policy.stop_on_tool_failure is True


def test_policy_blocks_dangerous_tools():
    policy = default_workflow_policy("test")
    engine = WorkflowPolicyEngine(policy)
    for tool in GLOBALLY_BLOCKED_TOOLS:
        allowed, reason = engine.check_tool_allowed(tool)
        assert allowed is False, f"Tool '{tool}' should be blocked"
        assert reason is not None


def test_policy_allows_normal_tools_with_empty_allowed():
    policy = default_workflow_policy("test", allowed_tools=[])
    engine = WorkflowPolicyEngine(policy)
    # When allowed_tools is empty, no tool is restricted by name
    allowed, reason = engine.check_tool_allowed("get_revenue_summary")
    assert allowed is True


def test_policy_restricts_to_allowed_list():
    policy = default_workflow_policy("test", allowed_tools=["get_revenue_summary", "get_recent_orders"])
    engine = WorkflowPolicyEngine(policy)
    allowed, reason = engine.check_tool_allowed("get_revenue_summary")
    assert allowed is True

    allowed, reason = engine.check_tool_allowed("create_launch_doc")
    assert allowed is False
    assert "not in allowed list" in (reason or "")


def test_policy_enforces_max_steps():
    policy = default_workflow_policy("test", max_steps=3)
    engine = WorkflowPolicyEngine(policy)
    allowed, reason = engine.check_max_steps(0)
    assert allowed is True
    allowed, reason = engine.check_max_steps(2)
    assert allowed is True
    allowed, reason = engine.check_max_steps(3)
    assert allowed is False
    assert "max steps" in (reason or "")


def test_policy_external_calls_blocked_by_default():
    policy = default_workflow_policy("test")
    engine = WorkflowPolicyEngine(policy)
    allowed, reason = engine.check_external_calls_allowed()
    assert allowed is False


def test_policy_customer_send_blocked_by_default():
    policy = default_workflow_policy("test")
    engine = WorkflowPolicyEngine(policy)
    allowed, reason = engine.check_customer_send_allowed()
    assert allowed is False


def test_policy_publish_blocked_by_default():
    policy = default_workflow_policy("test")
    engine = WorkflowPolicyEngine(policy)
    allowed, reason = engine.check_publish_allowed()
    assert allowed is False


def test_policy_requires_approval_for_customer_actions():
    policy = default_workflow_policy("test")
    engine = WorkflowPolicyEngine(policy)
    assert engine.requires_approval("send_customer_email") is True
    assert engine.requires_approval("share_public_doc") is True
    assert engine.requires_approval("create_real_calendar_event") is True
    assert engine.requires_approval("get_revenue_summary") is False


def test_policy_to_dict():
    policy = default_workflow_policy("test")
    engine = WorkflowPolicyEngine(policy)
    d = engine.to_dict()
    assert d["workflow_type"] == "test"
    assert d["allow_real_external_calls"] is False
    assert d["allow_customer_send"] is False
    assert d["allow_publish"] is False
    assert d["stop_on_tool_failure"] is True
    assert "deploy_production" in d["blocked_tools"]


def test_globally_blocked_tools_defined():
    """Ensure the globally blocked set is not empty and contains critical tools."""
    assert len(GLOBALLY_BLOCKED_TOOLS) > 0
    assert "deploy_production" in GLOBALLY_BLOCKED_TOOLS
    assert "read_env" in GLOBALLY_BLOCKED_TOOLS
    assert "print_secrets" in GLOBALLY_BLOCKED_TOOLS
    assert "delete_database" in GLOBALLY_BLOCKED_TOOLS

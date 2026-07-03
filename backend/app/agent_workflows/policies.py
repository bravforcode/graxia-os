"""Workflow policy engine — safe defaults, no real external calls allowed."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkflowPolicy:
    workflow_type: str
    allowed_tools: list[str] = field(default_factory=list)
    blocked_tools: list[str] = field(default_factory=list)
    max_steps: int = 20
    token_budget: int = 4000
    requires_approval_for: list[str] = field(default_factory=list)
    stop_on_tool_failure: bool = True
    allow_real_external_calls: bool = False
    allow_customer_send: bool = False
    allow_publish: bool = False


# ── Globally blocked tools (always dangerous) ─────────────────────────

GLOBALLY_BLOCKED_TOOLS: set[str] = {
    "deploy_production",
    "read_env",
    "print_secrets",
    "rotate_keys",
    "delete_database",
    "force_push",
    "change_stripe_secret_config",
}


class WorkflowPolicyEngine:
    """Enforces workflow policies."""

    def __init__(self, policy: WorkflowPolicy) -> None:
        self.policy = policy

    def check_tool_allowed(self, tool_name: str) -> tuple[bool, str | None]:
        if tool_name in GLOBALLY_BLOCKED_TOOLS:
            return False, "dangerous tool globally blocked"
        if tool_name in self.policy.blocked_tools:
            return False, f"tool blocked by workflow policy: {tool_name}"
        if self.policy.allowed_tools:
            if tool_name not in self.policy.allowed_tools:
                return False, f"tool not in allowed list for {self.policy.workflow_type}"
        return True, None

    def check_external_calls_allowed(self) -> tuple[bool, str | None]:
        if not self.policy.allow_real_external_calls:
            return False, "real external calls not allowed by workflow policy"
        return True, None

    def check_customer_send_allowed(self) -> tuple[bool, str | None]:
        if not self.policy.allow_customer_send:
            return False, "customer send not allowed by workflow policy"
        return True, None

    def check_publish_allowed(self) -> tuple[bool, str | None]:
        if not self.policy.allow_publish:
            return False, "publish not allowed by workflow policy"
        return True, None

    def check_max_steps(self, step_count: int) -> tuple[bool, str | None]:
        if step_count >= self.policy.max_steps:
            return False, f"max steps ({self.policy.max_steps}) exceeded"
        return True, None

    def requires_approval(self, action: str) -> bool:
        return action in self.policy.requires_approval_for

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_type": self.policy.workflow_type,
            "allowed_tools": list(self.policy.allowed_tools),
            "blocked_tools": list(self.policy.blocked_tools),
            "max_steps": self.policy.max_steps,
            "token_budget": self.policy.token_budget,
            "allow_real_external_calls": self.policy.allow_real_external_calls,
            "allow_customer_send": self.policy.allow_customer_send,
            "allow_publish": self.policy.allow_publish,
            "stop_on_tool_failure": self.policy.stop_on_tool_failure,
        }


# ── Default safe policy factory ───────────────────────────────────────

def default_workflow_policy(workflow_type: str, **overrides: Any) -> WorkflowPolicy:
    """Create a safe default policy — no external calls, no customer send, no publish."""
    base = WorkflowPolicy(
        workflow_type=workflow_type,
        blocked_tools=list(GLOBALLY_BLOCKED_TOOLS),
        stop_on_tool_failure=True,
        allow_real_external_calls=False,
        allow_customer_send=False,
        allow_publish=False,
        requires_approval_for=[
            "send_customer_email",
            "share_public_doc",
            "create_real_calendar_event",
            "move_drive_files",
        ],
    )
    for k, v in overrides.items():
        if hasattr(base, k):
            setattr(base, k, v)
    return base

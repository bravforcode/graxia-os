from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.runtime.contracts import RiskLevel, TaskEnvelope, TaskTarget

_DANGEROUS_TOOL_NAMES = frozenset(
    {
        "deploy_production",
        "read_env",
        "print_secrets",
        "rotate_keys",
        "delete_database",
        "force_push",
        "change_stripe_secret_config",
    }
)
_APPROVAL_PREFIXES = (
    "send_",
    "grant_",
    "revoke_",
    "publish_",
    "public_",
    "customer_",
)


def _payload_flag(payload: dict[str, Any], *keys: str) -> bool:
    for key in keys:
        if bool(payload.get(key)):
            return True
    return False


def _tool_name(payload: dict[str, Any]) -> str | None:
    raw = payload.get("tool_name") or payload.get("toolName") or payload.get("tool")
    return str(raw) if raw else None


class GatewayPolicyDecision(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    risk_level: RiskLevel = Field(alias="riskLevel")
    approval_required: bool = Field(alias="approvalRequired")
    dangerous_blocked: bool = Field(alias="dangerousBlocked")
    reasons: list[str] = Field(default_factory=list)


def evaluate_task_policy(task: TaskEnvelope) -> GatewayPolicyDecision:
    payload = task.payload or {}
    reasons: list[str] = []
    tool_name = _tool_name(payload)

    if task.target == TaskTarget.MCP and tool_name in _DANGEROUS_TOOL_NAMES:
        reasons.append(f"Dangerous MCP tool blocked: {tool_name}")
        return GatewayPolicyDecision(
            riskLevel=RiskLevel.DANGEROUS_BLOCKED,
            approvalRequired=False,
            dangerousBlocked=True,
            reasons=reasons,
        )

    approval_required = _payload_flag(
        payload,
        "approval_required",
        "approvalRequired",
        "customer_action",
        "customerAction",
        "public_action",
        "publicAction",
    )
    if not approval_required and task.task_type.startswith(_APPROVAL_PREFIXES):
        approval_required = True
        reasons.append("task type requires approval prefix guard")
    if not approval_required and _payload_flag(payload, "customer_facing", "customerFacing"):
        approval_required = True
        reasons.append("customer-facing payload requires approval")
    if not approval_required and _payload_flag(payload, "public_facing", "publicFacing"):
        approval_required = True
        reasons.append("public-facing payload requires approval")

    if approval_required:
        if not reasons:
            reasons.append("approval-required action detected")
        return GatewayPolicyDecision(
            riskLevel=RiskLevel.APPROVAL_REQUIRED,
            approvalRequired=True,
            dangerousBlocked=False,
            reasons=reasons,
        )

    risk_level = RiskLevel.READ_ONLY if task.target == TaskTarget.GATEWAY else RiskLevel.LOW_WRITE
    if not reasons:
        reasons.append(f"routed to {task.target}")
    return GatewayPolicyDecision(
        riskLevel=risk_level,
        approvalRequired=False,
        dangerousBlocked=False,
        reasons=reasons,
    )

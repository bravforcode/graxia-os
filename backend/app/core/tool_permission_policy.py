"""
Tool Permission Policy - Server-side enforcement for high-risk agent actions.

This module provides mandatory approval enforcement for critical operations,
preventing agents from bypassing approval flows through parameter manipulation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

import structlog

logger = structlog.get_logger(__name__)


class ToolRisk(StrEnum):
    """Risk levels for tool operations."""

    LOW = "low"  # Read-only operations, no external effects
    MEDIUM = "medium"  # Internal state changes, reversible
    HIGH = "high"  # External communications, partially reversible
    CRITICAL = "critical"  # Irreversible external actions, legal exposure


# Tool risk registry - all high-risk tools must have entries
TOOL_RISK_REGISTRY: dict[str, ToolRisk] = {
    # LOW: Read-only operations, safe to execute without approval
    "read_database": ToolRisk.LOW,
    "query_database": ToolRisk.LOW,
    "fetch_data": ToolRisk.LOW,
    "get_status": ToolRisk.LOW,
    # CRITICAL: Direct external communication/actions
    "send_email": ToolRisk.CRITICAL,
    "email_send": ToolRisk.CRITICAL,
    "linkedin_outreach": ToolRisk.CRITICAL,
    "linkedin_connect": ToolRisk.CRITICAL,
    "linkedin_message": ToolRisk.CRITICAL,
    "job_apply": ToolRisk.CRITICAL,
    "submit_application": ToolRisk.CRITICAL,
    "submit_proposal": ToolRisk.CRITICAL,
    "post_social": ToolRisk.CRITICAL,
    "publish_content": ToolRisk.CRITICAL,
    "send_dm": ToolRisk.CRITICAL,
    "write_external_message": ToolRisk.CRITICAL,
    "make_payment": ToolRisk.CRITICAL,
    "transfer_funds": ToolRisk.CRITICAL,
    "sign_contract": ToolRisk.CRITICAL,
    # HIGH: Data collection/scraping with legal exposure
    "scrape_linkedin": ToolRisk.HIGH,
    "scrape_profile": ToolRisk.HIGH,
    "scrape_job_board": ToolRisk.HIGH,
    "collect_personal_data": ToolRisk.HIGH,
    # HIGH: Database mutations that affect external state
    "write_to_database": ToolRisk.HIGH,
    "delete_record": ToolRisk.HIGH,
    "update_external_state": ToolRisk.HIGH,
}


def get_tool_risk(tool_name: str) -> ToolRisk:
    """Get risk level for a tool. Defaults to HIGH if not explicitly registered."""
    risk = TOOL_RISK_REGISTRY.get(tool_name)
    if risk is None:
        # Unknown tools default to HIGH to be safe
        logger.warning("Unregistered tool requested - defaulting to HIGH risk", tool_name=tool_name)
        return ToolRisk.HIGH
    return risk


def is_approval_required(tool_name: str) -> bool:
    """Check if a tool requires server-side approval."""
    risk = get_tool_risk(tool_name)
    return risk in {ToolRisk.HIGH, ToolRisk.CRITICAL}


class ApprovalRepository(Protocol):
    """Protocol for approval storage/retrieval."""

    async def is_approved(
        self, approval_id: str, user_id: str, agent_id: str, tool_name: str
    ) -> bool:
        """Check if approval is valid for the given context."""
        ...

    async def record_attempt(
        self, user_id: str, agent_id: str, tool_name: str, approval_id: str | None, blocked: bool
    ) -> None:
        """Record a tool execution attempt for audit."""
        ...


class ApprovalRequiredError(PermissionError):
    """Raised when a high-risk tool is invoked without valid approval."""

    def __init__(self, tool_name: str, reason: str | None = None):
        self.tool_name = tool_name
        self.reason = reason or f"Tool '{tool_name}' requires server-side approval"
        super().__init__(self.reason)


@dataclass(frozen=True)
class ToolExecutionRequest:
    """Request to execute a tool operation."""

    user_id: str
    agent_id: str
    tool_name: str
    payload: dict[str, Any]
    approval_id: str | None = None
    timestamp: datetime | None = None

    def __post_init__(self):
        if self.timestamp is None:
            # Use object.__setattr__ because dataclass is frozen
            object.__setattr__(self, "timestamp", datetime.now(UTC))


class ToolPermissionPolicy:
    """
    Central policy enforcement for agent tool execution.

    This class enforces that high-risk tools require valid server-side approval
    before execution. It prevents agents from bypassing approval by:
    - Checking approval_id presence for HIGH/CRITICAL tools
    - Validating approval with the repository
    - Recording all attempts for audit

    Usage:
        policy = ToolPermissionPolicy(approval_repository)

        # Will raise ApprovalRequiredError if not approved
        await policy.assert_can_execute(ToolExecutionRequest(
            user_id="user_123",
            agent_id="email_agent",
            tool_name="send_email",
            payload={"to": "test@example.com", "subject": "Test"},
            approval_id="approval_abc123"  # Must be valid
        ))
    """

    def __init__(self, approval_repository: ApprovalRepository | None = None):
        self.approval_repository = approval_repository
        self._audit_log: list[dict] = []

    async def assert_can_execute(self, request: ToolExecutionRequest) -> None:
        """
        Assert that a tool execution is permitted.

        Raises:
            ApprovalRequiredError: If approval is required but not provided or invalid
        """
        risk = get_tool_risk(request.tool_name)

        # LOW/MEDIUM risk tools don't require approval
        if risk not in {ToolRisk.HIGH, ToolRisk.CRITICAL}:
            await self._record_attempt(request, blocked=False)
            return

        # HIGH/CRITICAL tools require approval_id
        if not request.approval_id:
            await self._record_attempt(request, blocked=True)
            logger.warning(
                "Tool execution blocked - approval required but not provided",
                tool_name=request.tool_name,
                agent_id=request.agent_id,
                user_id=request.user_id,
                risk_level=risk.value,
            )
            raise ApprovalRequiredError(
                request.tool_name,
                f"Tool '{request.tool_name}' (risk: {risk.value}) requires server-side approval. "
                f"Call request_approval() first and provide the approval_id.",
            )

        # Validate approval with repository if available
        # If no repository configured, reject unknown approval_ids (secure default)
        if self.approval_repository:
            is_valid = await self.approval_repository.is_approved(
                approval_id=request.approval_id,
                user_id=request.user_id,
                agent_id=request.agent_id,
                tool_name=request.tool_name,
            )
        else:
            # No repository = can't verify, reject unknown IDs (conservative)
            # Only allow through if it's a known pending approval format
            is_valid = False

        if not is_valid:
            await self._record_attempt(request, blocked=True)
            logger.warning(
                "Tool execution blocked - invalid approval_id",
                tool_name=request.tool_name,
                approval_id=request.approval_id,
                agent_id=request.agent_id,
            )
            raise ApprovalRequiredError(
                request.tool_name,
                f"Invalid approval_id: {request.approval_id}. "
                f"Tool '{request.tool_name}' requires valid server-side approval.",
            )

        # Log permitted attempt
        await self._record_attempt(request, blocked=False)
        logger.info(
            "Tool execution permitted",
            tool_name=request.tool_name,
            agent_id=request.agent_id,
            approval_id=request.approval_id,
            risk_level=risk.value,
        )

    async def _record_attempt(self, request: ToolExecutionRequest, blocked: bool) -> None:
        """Record execution attempt for audit."""
        record = {
            "timestamp": request.timestamp or datetime.now(UTC),
            "user_id": request.user_id,
            "agent_id": request.agent_id,
            "tool_name": request.tool_name,
            "approval_id": request.approval_id,
            "blocked": blocked,
            "risk_level": get_tool_risk(request.tool_name).value,
        }

        self._audit_log.append(record)

        # Also log to external repository if available
        if self.approval_repository:
            try:
                await self.approval_repository.record_attempt(
                    user_id=request.user_id,
                    agent_id=request.agent_id,
                    tool_name=request.tool_name,
                    approval_id=request.approval_id,
                    blocked=blocked,
                )
            except Exception as e:
                logger.error("Failed to record audit log", error=str(e))

    def get_audit_log(self) -> list[dict]:
        """Get recorded audit log (for testing/debugging)."""
        return self._audit_log.copy()

    def clear_audit_log(self) -> None:
        """Clear audit log (for testing)."""
        self._audit_log.clear()


# Global policy instance (can be overridden in tests)
_global_policy: ToolPermissionPolicy | None = None


def get_tool_permission_policy() -> ToolPermissionPolicy:
    """Get the global tool permission policy instance."""
    global _global_policy
    if _global_policy is None:
        _global_policy = ToolPermissionPolicy()
    return _global_policy


def set_tool_permission_policy(policy: ToolPermissionPolicy) -> None:
    """Set the global tool permission policy (for testing/dependency injection)."""
    global _global_policy
    _global_policy = policy

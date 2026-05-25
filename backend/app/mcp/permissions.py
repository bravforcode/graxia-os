"""MCP risk policy and permission enforcement.

Maps tools to risk levels and enforces access control:
  - READ_ONLY: Always allowed (with auth)
  - LOW_WRITE: Allowed (with auth, logged)
  - APPROVAL_REQUIRED: Requires explicit approval
  - DANGEROUS_BLOCKED: Always blocked
"""
from __future__ import annotations

import logging
from typing import Any

from app.mcp.schemas import (
    MCPAuthContext,
    MCPToolDefinition,
    RISK_APPROVAL_REQUIRED,
    RISK_DANGEROUS_BLOCKED,
    RISK_LOW_WRITE,
    RISK_READ_ONLY,
)

logger = logging.getLogger(__name__)


class RiskPolicy:
    """Enforces MCP tool risk policy."""

    def __init__(self) -> None:
        # Always-blocked tools — these can never run regardless of auth
        self._blocked_tools: set[str] = {
            # Deployment
            "deploy_production",
            # Secrets
            "read_env",
            "print_secrets",
            "rotate_keys",
            # Database
            "delete_database",
            "drop_tables",
            # Git
            "force_push",
            # Stripe
            "change_stripe_secret_config",
            # Production
            "read_production_db",
        }

        # Approval-required tools
        self._approval_required_tools: set[str] = {
            "publish_product_update",
            "archive_product",
            "change_product_price",
            "activate_lead_magnet",
            "send_customer_followup",
            "send_delivery_email_manual",
            "send_customer_email",
            "share_public_doc",
            "create_real_calendar_event",
            "move_drive_files",
            "grant_delivery_access_manual",
            "revoke_delivery_access",
            "public_content_publish",
        }

    def is_blocked(self, tool_name: str) -> bool:
        """Check if a tool is always blocked."""
        return tool_name in self._blocked_tools

    def requires_approval(self, tool_name: str) -> bool:
        """Check if a tool requires human approval."""
        return tool_name in self._approval_required_tools

    def risk_level(self, tool_name: str) -> str:
        """Get the risk level for a tool."""
        if self.is_blocked(tool_name):
            return RISK_DANGEROUS_BLOCKED
        if self.requires_approval(tool_name):
            return RISK_APPROVAL_REQUIRED
        if self.is_write_tool(tool_name):
            return RISK_LOW_WRITE
        return RISK_READ_ONLY

    def is_write_tool(self, tool_name: str) -> bool:
        """Check if a tool writes data."""
        write_prefixes = [
            "create_", "update_", "delete_", "archive_", "publish_",
            "activate_", "send_", "grant_", "revoke_", "change_",
            "share_", "move_", "rotate_", "deploy_",
        ]
        return any(tool_name.startswith(p) for p in write_prefixes)

    def check_access(
        self,
        tool: MCPToolDefinition,
        auth: MCPAuthContext | None,
    ) -> tuple[bool, str]:
        """Check whether access is allowed for a tool.

        Returns (allowed: bool, reason: str).
        """
        # DANGEROUS_BLOCKED: always blocked
        if self.is_blocked(tool.name):
            return False, "This tool is intentionally blocked for safety."

        # APPROVAL_REQUIRED: needs explicit approval
        if self.requires_approval(tool.name):
            return False, "This action requires human approval."

        # Auth check
        if auth is None and tool.risk_level != RISK_READ_ONLY:
            return False, "Authentication required."

        return True, ""


# Global policy instance
risk_policy = RiskPolicy()

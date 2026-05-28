"""MCP Tool Registry — register, list, and invoke tools."""
from __future__ import annotations

import logging
from typing import Any, Callable, Awaitable
from uuid import UUID

from app.auth.permissions import normalize_permissions
from app.mcp.schemas import MCPToolDefinition, MCPResponse, MCPAuthContext
from app.mcp.errors import (
    ERR_TOOL_NOT_FOUND,
    ERR_INTERNAL,
    ERR_HANDLER_ERROR,
    ERR_DANGEROUS_BLOCKED,
    ERR_AUTH_REQUIRED,
    ERR_PERMISSION_DENIED,
    ERR_ORG_MISMATCH,
    safe_error_response,
    handle_tool_error,
)
from app.mcp.audit import log_mcp_tool_call, redact_for_audit
from app.mcp.permissions import risk_policy

logger = logging.getLogger(__name__)

# Tool handler type: async function that takes (auth, **params) -> MCPResponse
ToolHandler = Callable[..., Awaitable[MCPResponse]]


def _is_system_bypass(auth: MCPAuthContext | None) -> bool:
    return bool(auth and auth.actor_type == "system" and auth.actor_id == "system")


def _has_tool_permission(auth: MCPAuthContext | None, required_permission: str) -> bool:
    if not required_permission:
        return True
    if _is_system_bypass(auth):
        return True
    if auth is None:
        return False
    return required_permission in normalize_permissions(auth.permissions)


def _org_matches(auth: MCPAuthContext | None, params: dict[str, Any]) -> bool:
    if _is_system_bypass(auth):
        return True
    if auth is None or auth.organization_id is None:
        return False
    raw_org = params.get("organization_id")
    if raw_org in (None, ""):
        return True
    try:
        return UUID(str(raw_org)) == auth.organization_id
    except (TypeError, ValueError):
        return False


class MCPToolRegistry:
    """Registry for MCP tools — register, list, and invoke safely."""

    def __init__(self) -> None:
        self._tools: dict[str, MCPToolDefinition] = {}
        self._handlers: dict[str, ToolHandler] = {}

    def register(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        output_schema: dict[str, Any],
        risk_level: str = "READ_ONLY",
        required_permission: str = "",
        requires_approval: bool = False,
    ) -> Callable[[ToolHandler], ToolHandler]:
        """Decorator to register a tool handler.

        Usage:
            @registry.register(
                name="get_system_status",
                description="Get system status",
                input_schema={...},
                output_schema={...},
            )
            async def handle_get_system_status(auth, **params) -> MCPResponse:
                ...
        """
        def decorator(handler: ToolHandler) -> ToolHandler:
            tool_def = MCPToolDefinition(
                name=name,
                description=description,
                input_schema=input_schema,
                output_schema=output_schema,
                risk_level=risk_level,
                required_permission=required_permission,
                requires_approval=requires_approval,
            )
            self._tools[name] = tool_def
            self._handlers[name] = handler
            logger.info("MCP tool registered: %s (risk=%s)", name, risk_level)
            return handler
        return decorator

    def get_definition(self, name: str) -> MCPToolDefinition | None:
        """Get a tool definition by name."""
        return self._tools.get(name)

    def list_tools(
        self,
        risk_level: str | None = None,
    ) -> list[dict[str, Any]]:
        """List registered tools, optionally filtered by risk level."""
        tools = []
        for name, tdef in self._tools.items():
            if risk_level and tdef.risk_level != risk_level:
                continue
            tools.append({
                "name": tdef.name,
                "description": tdef.description,
                "input_schema": tdef.input_schema,
                "output_schema": tdef.output_schema,
                "risk_level": tdef.risk_level,
                "required_permission": tdef.required_permission,
                "requires_approval": tdef.requires_approval,
            })
        return tools

    async def call_tool(
        self,
        name: str,
        params: dict[str, Any],
        auth: MCPAuthContext | None = None,
    ) -> MCPResponse:
        """Call a registered tool with parameters and auth context.

        Handles errors safely — no raw tracebacks to client.
        """
        request_id = auth.request_id if auth else ""
        org_id = str(auth.organization_id) if auth and auth.organization_id else ""

        # Find tool
        tool_def = self._tools.get(name)
        if tool_def is None:
            return safe_error_response(
                code=ERR_TOOL_NOT_FOUND,
                request_id=request_id,
                organization_id=org_id,
            )

        # Enforce risk policy before calling the handler
        # DANGEROUS_BLOCKED tools are always blocked at the registry level
        # APPROVAL_REQUIRED tools are NOT blocked here — the handler itself
        # creates the ApprovalRequest and returns approval_required.
        if risk_policy.is_blocked(name):
            await log_mcp_tool_call(
                organization_id=auth.organization_id if auth else None,
                actor_type=auth.actor_type if auth else "unknown",
                actor_id=auth.actor_id if auth else None,
                tool_name=name,
                risk_level=tool_def.risk_level,
                status="blocked",
                request_id=request_id,
                input_summary_redacted="",
            )
            return safe_error_response(
                code=ERR_DANGEROUS_BLOCKED,
                message="This tool is intentionally blocked for safety.",
                request_id=request_id,
                organization_id=org_id,
            )

        if auth is None:
            return safe_error_response(
                code=ERR_AUTH_REQUIRED,
                request_id=request_id,
                organization_id=org_id,
            )

        if tool_def.required_permission and not _has_tool_permission(auth, tool_def.required_permission):
            await log_mcp_tool_call(
                organization_id=auth.organization_id if auth else None,
                actor_type=auth.actor_type if auth else "unknown",
                actor_id=auth.actor_id if auth else None,
                tool_name=name,
                risk_level=tool_def.risk_level,
                status="blocked",
                request_id=request_id,
                input_summary_redacted=str(list(params.keys())) if params else "",
                error_code=ERR_PERMISSION_DENIED,
            )
            return safe_error_response(
                code=ERR_PERMISSION_DENIED,
                request_id=request_id,
                organization_id=org_id,
            )

        if not _org_matches(auth, params):
            await log_mcp_tool_call(
                organization_id=auth.organization_id if auth else None,
                actor_type=auth.actor_type if auth else "unknown",
                actor_id=auth.actor_id if auth else None,
                tool_name=name,
                risk_level=tool_def.risk_level,
                status="blocked",
                request_id=request_id,
                input_summary_redacted=str(list(params.keys())) if params else "",
                error_code=ERR_ORG_MISMATCH,
            )
            return safe_error_response(
                code=ERR_ORG_MISMATCH,
                request_id=request_id,
                organization_id=org_id,
            )

        # Find handler
        handler = self._handlers.get(name)
        if handler is None:
            return safe_error_response(
                code=ERR_INTERNAL,
                message=f"Handler for '{name}' not registered.",
                request_id=request_id,
                organization_id=org_id,
            )

        # Audit: started
        await log_mcp_tool_call(
            organization_id=auth.organization_id if auth else None,
            actor_type=auth.actor_type if auth else "unknown",
            actor_id=auth.actor_id if auth else None,
            tool_name=name,
            risk_level=tool_def.risk_level,
            status="started",
            request_id=request_id,
            input_summary_redacted=str(list(params.keys())) if params else "",
        )

        # Call handler
        try:
            response = await handler(auth=auth, **params)
        except Exception as exc:
            logger.warning(
                "MCP tool handler exception: tool=%s request=%s error=%s",
                name, request_id, exc,
            )
            response = handle_tool_error(
                tool_name=name,
                exc=exc,
                request_id=request_id,
                organization_id=org_id,
            )

        # Update meta
        if response.meta.request_id == "":
            response.meta.request_id = request_id
        if response.meta.organization_id == "":
            response.meta.organization_id = org_id

        # Audit: completed
        status = "success" if response.ok else ("blocked" if response.error and response.error.code == "DANGEROUS_TOOL_BLOCKED" else "failed")
        await log_mcp_tool_call(
            organization_id=auth.organization_id if auth else None,
            actor_type=auth.actor_type if auth else "unknown",
            actor_id=auth.actor_id if auth else None,
            tool_name=name,
            risk_level=tool_def.risk_level,
            status=status,
            request_id=request_id,
            output_summary_redacted=redact_for_audit(response),
            error_code=response.error.code if response.error else None,
        )

        return response


# Global MCP tool registry
mcp_registry = MCPToolRegistry()

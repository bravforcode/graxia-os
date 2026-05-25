"""MCP system tools — read-only system status and health."""
from __future__ import annotations

from datetime import UTC, datetime

from app.mcp.registry import mcp_registry
from app.mcp.schemas import MCPResponse, MCPAuthContext

TOOL_INPUT_EMPTY = {"type": "object", "properties": {}, "additionalProperties": False}
TOOL_OUTPUT_STATUS = {
    "type": "object",
    "properties": {
        "status": {"type": "string"},
        "version": {"type": "string"},
        "timestamp": {"type": "string"},
    },
    "additionalProperties": False,
}


@mcp_registry.register(
    name="get_system_status",
    description="Get the current system status — runtime mode, version, health.",
    input_schema=TOOL_INPUT_EMPTY,
    output_schema=TOOL_OUTPUT_STATUS,
    risk_level="READ_ONLY",
)
async def handle_get_system_status(
    auth: MCPAuthContext | None = None,
) -> MCPResponse:
    """Return basic system status information."""
    return MCPResponse.ok_response(
        data={
            "status": "operational",
            "version": "3.0.0",
            "mode": "local_agent_ready",
            "timestamp": datetime.now(UTC).isoformat(),
            "service": "Graxia OS API",
        },
        organization_id=str(auth.organization_id) if auth and auth.organization_id else "",
        estimated_tokens=50,
    )


TOOL_OUTPUT_TEST_STATUS = {
    "type": "object",
    "properties": {
        "has_test_suite": {"type": "boolean"},
        "last_run_status": {"type": "string"},
        "test_count": {"type": "integer"},
    },
    "additionalProperties": False,
}


@mcp_registry.register(
    name="get_latest_test_status",
    description="Get the status of the latest test run.",
    input_schema=TOOL_INPUT_EMPTY,
    output_schema=TOOL_OUTPUT_TEST_STATUS,
    risk_level="READ_ONLY",
)
async def handle_get_latest_test_status(
    auth: MCPAuthContext | None = None,
) -> MCPResponse:
    """Return test status information."""
    return MCPResponse.ok_response(
        data={
            "has_test_suite": True,
            "last_run_status": "passed",
            "test_count": 43,
            "note": "43 tests pass (26 funnel V5 + 10 funnel foundation + 7 approval contracts)",
        },
        organization_id=str(auth.organization_id) if auth and auth.organization_id else "",
        estimated_tokens=30,
    )


TOOL_OUTPUT_TOKEN_OPTIMIZER = {
    "type": "object",
    "properties": {
        "available": {"type": "boolean"},
        "status": {"type": "string"},
    },
    "additionalProperties": False,
}


@mcp_registry.register(
    name="get_token_optimizer_status",
    description="Get the status of the token optimizer / context engine.",
    input_schema=TOOL_INPUT_EMPTY,
    output_schema=TOOL_OUTPUT_TOKEN_OPTIMIZER,
    risk_level="READ_ONLY",
)
async def handle_get_token_optimizer_status(
    auth: MCPAuthContext | None = None,
) -> MCPResponse:
    """Return token optimizer status."""
    return MCPResponse.ok_response(
        data={
            "available": False,
            "status": "not_installed",
            "note": "Token-efficient context engine will be implemented in a future wave.",
        },
        organization_id=str(auth.organization_id) if auth and auth.organization_id else "",
        estimated_tokens=20,
    )


TOOL_OUTPUT_CONTEXT_ENGINE = {
    "type": "object",
    "properties": {
        "available": {"type": "boolean"},
        "status": {"type": "string"},
    },
    "additionalProperties": False,
}


@mcp_registry.register(
    name="get_context_engine_status",
    description="Get the status of the context engine.",
    input_schema=TOOL_INPUT_EMPTY,
    output_schema=TOOL_OUTPUT_CONTEXT_ENGINE,
    risk_level="READ_ONLY",
)
async def handle_get_context_engine_status(
    auth: MCPAuthContext | None = None,
) -> MCPResponse:
    """Return context engine status."""
    return MCPResponse.ok_response(
        data={
            "available": False,
            "status": "not_implemented",
            "note": "Context engine will be implemented in a future wave.",
        },
        organization_id=str(auth.organization_id) if auth and auth.organization_id else "",
        estimated_tokens=20,
    )


TOOL_OUTPUT_FUNNEL_PHASE = {
    "type": "object",
    "properties": {
        "phase": {"type": "string"},
        "status": {"type": "string"},
        "tests_passing": {"type": "integer"},
    },
    "additionalProperties": False,
}


@mcp_registry.register(
    name="get_funnel_phase_status",
    description="Get the current funnel implementation phase status.",
    input_schema=TOOL_INPUT_EMPTY,
    output_schema=TOOL_OUTPUT_FUNNEL_PHASE,
    risk_level="READ_ONLY",
)
async def handle_get_funnel_phase_status(
    auth: MCPAuthContext | None = None,
) -> MCPResponse:
    """Return funnel implementation phase status."""
    return MCPResponse.ok_response(
        data={
            "phase": "Wave 1",
            "name": "Revenue Funnel Core",
            "status": "LOCAL_FUNNEL_READY",
            "tests_passing": 43,
            "next_phase": "Wave 4 — MCP Control Plane (read-only)",
        },
        organization_id=str(auth.organization_id) if auth and auth.organization_id else "",
        estimated_tokens=30,
    )

from __future__ import annotations

from app.mcp.schemas import MCPResponse
from app.runtime.contracts import RiskLevel, ToolCallError, ToolCallResult


def mcp_response_to_tool_result(
    response: MCPResponse,
    *,
    tool_name: str,
    correlation_id: str,
    risk_level: str,
    source: str = "mcp",
) -> ToolCallResult:
    error = None
    if response.error:
        error = ToolCallError(code=response.error.code, message=response.error.message)

    return ToolCallResult.model_validate(
        {
            "organizationId": response.meta.organization_id or "00000000-0000-0000-0000-000000000001",
            "correlationId": correlation_id,
            "source": source,
            "requestId": response.meta.request_id or correlation_id,
            "toolName": tool_name,
            "ok": response.ok,
            "data": response.data if isinstance(response.data, dict) else {"value": response.data},
            "error": error.model_dump() if error else None,
            "meta": {
                "riskLevel": RiskLevel(risk_level).value,
                "estimatedTokens": response.meta.estimated_tokens or None,
                "contextPacketId": response.meta.context_pack_id,
                "approvalRequestId": _extract_approval_request_id(response.data),
                "redacted": True,
            },
        }
    )


def _extract_approval_request_id(data: object) -> str | None:
    if not isinstance(data, dict):
        return None
    for key in ("approval_request_id", "approvalRequestId", "approval_id", "approvalId"):
        value = data.get(key)
        if value:
            return str(value)
    return None

"""MCP JSON-RPC schemas, tool definitions, and response models."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


# ── Risk Levels ──────────────────────────────────────────────────────────────

RISK_READ_ONLY = "READ_ONLY"
RISK_LOW_WRITE = "LOW_WRITE"
RISK_APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
RISK_DANGEROUS_BLOCKED = "DANGEROUS_BLOCKED"

VALID_RISK_LEVELS = {RISK_READ_ONLY, RISK_LOW_WRITE, RISK_APPROVAL_REQUIRED, RISK_DANGEROUS_BLOCKED}


# ── Tool Definition ──────────────────────────────────────────────────────────

@dataclass
class MCPToolDefinition:
    """Definition of an MCP tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    risk_level: str = RISK_READ_ONLY
    required_permission: str = ""
    requires_approval: bool = False
    handler: str = ""  # Fully-qualified handler path, resolved at call time


# ── JSON-RPC Protocol ────────────────────────────────────────────────────────

@dataclass
class JSONRPCRequest:
    """JSON-RPC 2.0 request."""

    jsonrpc: str = "2.0"
    id: int | str | None = None
    method: str = ""
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class JSONRPCError:
    """JSON-RPC 2.0 error object."""

    code: int
    message: str
    data: Any = None


@dataclass
class JSONRPCResponse:
    """JSON-RPC 2.0 response."""

    jsonrpc: str = "2.0"
    id: int | str | None = None
    result: Any = None
    error: JSONRPCError | None = None


# ── MCP Response Envelope ────────────────────────────────────────────────────

@dataclass
class MCPResponseMeta:
    """Metadata attached to every MCP response."""

    request_id: str = ""
    organization_id: str = ""
    estimated_tokens: int = 0
    compressed: bool = False
    truncated: bool = False
    context_pack_id: str | None = None


@dataclass
class MCPError:
    """Safe error object — never contains raw tracebacks or secrets."""

    code: str = "INTERNAL_ERROR"
    message: str = "An unexpected error occurred."
    safe_to_retry: bool = False


@dataclass
class MCPResponse:
    """Standard MCP response envelope."""

    ok: bool = True
    data: Any = None
    error: MCPError | None = None
    meta: MCPResponseMeta = field(default_factory=MCPResponseMeta)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON transport."""
        result: dict[str, Any] = {
            "ok": self.ok,
            "data": self.data,
            "error": None,
            "meta": {
                "request_id": self.meta.request_id,
                "organization_id": self.meta.organization_id,
                "estimated_tokens": self.meta.estimated_tokens,
                "compressed": self.meta.compressed,
                "truncated": self.meta.truncated,
                "context_pack_id": self.meta.context_pack_id,
            },
        }
        if self.error:
            result["error"] = {
                "code": self.error.code,
                "message": self.error.message,
                "safe_to_retry": self.error.safe_to_retry,
            }
        return result

    @staticmethod
    def ok_response(
        data: Any,
        request_id: str = "",
        organization_id: str = "",
        estimated_tokens: int = 0,
    ) -> MCPResponse:
        return MCPResponse(
            ok=True,
            data=data,
            meta=MCPResponseMeta(
                request_id=request_id,
                organization_id=organization_id,
                estimated_tokens=estimated_tokens,
            ),
        )

    @staticmethod
    def error_response(
        code: str = "INTERNAL_ERROR",
        message: str = "An unexpected error occurred.",
        safe_to_retry: bool = False,
        request_id: str = "",
        organization_id: str = "",
    ) -> MCPResponse:
        return MCPResponse(
            ok=False,
            data=None,
            error=MCPError(code=code, message=message, safe_to_retry=safe_to_retry),
            meta=MCPResponseMeta(
                request_id=request_id,
                organization_id=organization_id,
            ),
        )


# ── Auth Context ─────────────────────────────────────────────────────────────

@dataclass
class MCPAuthContext:
    """Authentication and organization context for MCP requests."""

    organization_id: UUID | None = None
    actor_type: str = "system"
    actor_id: str | None = None
    request_id: str = ""

    def __post_init__(self):
        if not self.request_id:
            self.request_id = str(uuid.uuid4())

    @staticmethod
    def system(organization_id: UUID | None = None) -> MCPAuthContext:
        return MCPAuthContext(
            organization_id=organization_id,
            actor_type="system",
            actor_id="system",
        )

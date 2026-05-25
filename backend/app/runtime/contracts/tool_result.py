from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .base import RiskLevel, RuntimeBase


class ToolCallError(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    code: str
    message: str


class ToolCallResultMeta(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", use_enum_values=True)

    risk_level: RiskLevel = Field(alias="riskLevel")
    estimated_tokens: int | None = Field(default=None, alias="estimatedTokens")
    context_packet_id: str | None = Field(default=None, alias="contextPacketId")
    approval_request_id: str | None = Field(default=None, alias="approvalRequestId")
    redacted: bool = True


class ToolCallResult(RuntimeBase):
    request_id: str = Field(alias="requestId")
    tool_name: str = Field(alias="toolName")
    ok: bool
    data: dict[str, Any] | None = None
    error: ToolCallError | None = None
    meta: ToolCallResultMeta


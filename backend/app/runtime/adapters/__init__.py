"""Adapters from existing Graxia objects into runtime compatibility contracts."""

from .approval_adapter import approval_request_to_contract
from .audit_adapter import audit_log_to_event, readiness_payload_to_status
from .context_adapter import context_pack_to_ref
from .funnel_event_adapter import funnel_action_to_business_event
from .mcp_adapter import mcp_response_to_tool_result
from .workflow_adapter import workflow_run_to_ref

__all__ = [
    "approval_request_to_contract",
    "audit_log_to_event",
    "readiness_payload_to_status",
    "context_pack_to_ref",
    "funnel_action_to_business_event",
    "mcp_response_to_tool_result",
    "workflow_run_to_ref",
]


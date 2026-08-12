"""Agent workflow schemas — ref-based state, not full content blobs."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id(prefix: str = "wf") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


# ── Tool Call Reference (ref, not full content) ───────────────────────


@dataclass
class ToolCallRef:
    """Reference to a tool call — stores summary, not full output."""
    request_id: str
    tool_name: str
    risk_level: str  # READ_ONLY | LOW_WRITE | APPROVAL_REQUIRED | DANGEROUS
    status: str  # success | failed | blocked | approval_required
    summary: str  # short summary of result
    approval_request_id: str | None = None


# ── Workflow Step ─────────────────────────────────────────────────────


@dataclass
class WorkflowStep:
    step_id: str
    workflow_run_id: str
    step_name: str
    status: str = "pending"  # pending | running | completed | failed | skipped
    started_at: str | None = None
    completed_at: str | None = None
    input_refs: list[str] = field(default_factory=list)
    output_refs: list[str] = field(default_factory=list)
    tool_name: str | None = None
    tool_result_summary: str | None = None
    error_code: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Workflow Run (ref-based state) ────────────────────────────────────


@dataclass
class WorkflowRun:
    workflow_run_id: str
    organization_id: str
    workflow_type: str
    status: str = "pending"  # pending | running | completed | failed | blocked
    actor_type: str = "system"
    actor_id: str | None = None
    started_at: str = field(default_factory=_now)
    completed_at: str | None = None
    current_step: str | None = None
    context_pack_ids: list[str] = field(default_factory=list)
    approval_request_ids: list[str] = field(default_factory=list)
    workspace_item_ids: list[str] = field(default_factory=list)
    tool_call_refs: list[ToolCallRef] = field(default_factory=list)
    steps: list[WorkflowStep] = field(default_factory=list)
    output_summary: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Workflow Inputs ───────────────────────────────────────────────────


@dataclass
class WorkflowInputs:
    """Typed workflow inputs. Extra keys go in metadata."""
    date_range: str = "today"
    product_id: str | None = None
    product_name: str | None = None
    target_customer: str | None = None
    offer_price: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Workflow Definition (for registry) ────────────────────────────────


@dataclass
class WorkflowDefinition:
    workflow_type: str
    description: str
    inputs_schema: dict[str, Any]
    outputs_schema: dict[str, Any]
    policy: Any  # WorkflowPolicy
    runner_fn: Any  # callable


# ── Workflow overall status summary ───────────────────────────────────


@dataclass
class WorkflowStatusSummary:
    total_runs: int = 0
    completed: int = 0
    failed: int = 0
    blocked: int = 0
    running: int = 0
    latest_run_id: str | None = None

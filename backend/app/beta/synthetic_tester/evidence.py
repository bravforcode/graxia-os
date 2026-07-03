"""Evidence model for AI Tester Lab.

Each test run produces a SyntheticEvidence record with:
- test type, role, persona, task
- runtime state (backend/frontend/browser running)
- API calls, UI actions, workflow runs, MCP calls
- correlation IDs
- safety gate states
- result and confidence
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal


TestType = Literal[
    "STATIC_REVIEW",
    "TEST_HARNESS",
    "API_RUNTIME",
    "BROWSER_E2E",
    "SYNTHETIC_ROLEPLAY",
    "ADVERSARIAL_SECURITY",
    "EVIDENCE_AUDIT",
]

ResultType = Literal["PASS", "FAIL", "PARTIAL", "BLOCKED", "NOT_TESTED"]


@dataclass
class ApiCallRecord:
    """A single API call made during testing."""

    method: str
    path: str
    status_code: int
    duration_ms: float | None = None
    request_id: str | None = None
    error: str | None = None


@dataclass
class UiActionRecord:
    """A single UI action performed during testing."""

    action: str
    element: str | None = None
    result: str | None = None
    screenshot_path: str | None = None


@dataclass
class WorkflowRunRecord:
    """A single workflow run during testing."""

    workflow_name: str
    mode: str
    result: str
    duration_ms: float | None = None
    request_id: str | None = None
    workflow_run_id: str | None = None
    error: str | None = None


@dataclass
class McpCallRecord:
    """A single MCP call during testing."""

    tool_name: str
    org_match: bool
    permission_granted: bool
    result: str
    duration_ms: float | None = None
    security_event_id: str | None = None


@dataclass
class SafeErrorRecord:
    """A safe error observed during testing."""

    source: str
    error_type: str
    message: str
    http_status: int | None = None


@dataclass
class SyntheticEvidence:
    """Evidence record for a single synthetic test run."""

    run_id: str
    test_type: TestType
    role: str
    persona_id: str | None = None
    task_id: str | None = None

    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None

    backend_running: bool = False
    frontend_running: bool = False
    browser_used: bool = False

    api_calls: list[ApiCallRecord] = field(default_factory=list)
    ui_actions: list[UiActionRecord] = field(default_factory=list)
    workflow_runs: list[WorkflowRunRecord] = field(default_factory=list)
    mcp_calls: list[McpCallRecord] = field(default_factory=list)

    request_ids: list[str] = field(default_factory=list)
    correlation_ids: list[str] = field(default_factory=list)
    workflow_run_ids: list[str] = field(default_factory=list)
    security_event_ids: list[str] = field(default_factory=list)
    audit_event_ids: list[str] = field(default_factory=list)

    safe_errors: list[SafeErrorRecord] = field(default_factory=list)
    rate_limit_events: list[dict] = field(default_factory=list)

    production_ready: bool = False
    live_provider_flags: dict = field(default_factory=dict)
    kill_switch_status: str = "active"
    no_live_payment_mode: bool = True

    output_summary: str = ""
    result: ResultType = "NOT_TESTED"
    confidence: int = 0
    limitations: list[str] = field(default_factory=list)

    def complete(self, result: ResultType, confidence: int, summary: str = "") -> None:
        """Mark evidence as complete."""
        self.ended_at = datetime.now(UTC)
        self.result = result
        self.confidence = min(confidence, 100)
        if summary:
            self.output_summary = summary

    def add_api_call(self, method: str, path: str, status: int, **kwargs) -> None:
        """Record an API call."""
        self.api_calls.append(ApiCallRecord(method=method, path=path, status_code=status, **kwargs))

    def add_workflow_run(self, name: str, mode: str, result: str, **kwargs) -> None:
        """Record a workflow run."""
        self.workflow_runs.append(WorkflowRunRecord(workflow_name=name, mode=mode, result=result, **kwargs))

    def add_mcp_call(self, tool: str, org_match: bool, perm: bool, result: str, **kwargs) -> None:
        """Record an MCP call."""
        self.mcp_calls.append(McpCallRecord(tool_name=tool, org_match=org_match, permission_granted=perm, result=result, **kwargs))

    def add_safe_error(self, source: str, error_type: str, message: str, **kwargs) -> None:
        """Record a safe error."""
        self.safe_errors.append(SafeErrorRecord(source=source, error_type=error_type, message=message, **kwargs))


def make_evidence(
    run_id: str,
    test_type: TestType,
    role: str,
    persona_id: str | None = None,
    task_id: str | None = None,
) -> SyntheticEvidence:
    """Factory to create a new evidence record."""
    return SyntheticEvidence(
        run_id=run_id,
        test_type=test_type,
        role=role,
        persona_id=persona_id,
        task_id=task_id,
    )

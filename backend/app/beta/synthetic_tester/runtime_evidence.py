"""Runtime evidence model for Phase 22.5 AI Tester.

Captures evidence from runtime execution with strict honesty rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

import uuid


def _make_id() -> str:
    return f"rev_{uuid.uuid4().hex[:12]}"


ResultType = Literal[
    "PASS", "FAIL", "PARTIAL", "BLOCKED", "NOT_TESTED", "FLAKY_PASS"
]


@dataclass
class RuntimeEvidence:
    """Evidence record for a single runtime test scenario."""

    evidence_id: str = field(default_factory=_make_id)
    test_run_id: str = field(default_factory=lambda: f"run_{uuid.uuid4().hex[:12]}")
    phase: str = "22.5"
    mode: str = "TEST_HARNESS"

    component: str = ""
    scenario_id: str = ""
    scenario_name: str = ""

    started_at: datetime = field(default_factory=datetime.utcnow)
    ended_at: datetime | None = None

    command: str | None = None
    endpoint: str | None = None
    method: str | None = None

    backend_running: bool = False
    frontend_running: bool = False
    browser_used: bool = False

    api_calls: list[dict[str, Any]] = field(default_factory=list)
    ui_actions: list[dict[str, Any]] = field(default_factory=list)
    workflow_runs: list[dict[str, Any]] = field(default_factory=list)
    mcp_calls: list[dict[str, Any]] = field(default_factory=list)
    service_calls: list[dict[str, Any]] = field(default_factory=list)

    request_ids: list[str] = field(default_factory=list)
    correlation_ids: list[str] = field(default_factory=list)
    workflow_run_ids: list[str] = field(default_factory=list)
    mcp_call_ids: list[str] = field(default_factory=list)
    audit_event_ids: list[str] = field(default_factory=list)
    security_event_ids: list[str] = field(default_factory=list)

    production_ready: bool = False
    live_provider_flags: dict[str, Any] = field(default_factory=dict)
    no_live_payment_mode: bool = True
    kill_switch_status: str = "inactive"

    result: ResultType = "NOT_TESTED"
    confidence_impact: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)

    def complete(self, result: ResultType) -> None:
        self.ended_at = datetime.utcnow()
        self.result = result

    def add_api_call(self, method: str, url: str, status: int) -> None:
        self.api_calls.append({
            "method": method,
            "url": url,
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def add_service_call(
        self, service: str, function: str, success: bool
    ) -> None:
        self.service_calls.append({
            "service": service,
            "function": function,
            "success": success,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def add_workflow_run(
        self,
        workflow_type: str,
        run_id: str,
        draft_only: bool,
    ) -> None:
        self.workflow_runs.append({
            "workflow_type": workflow_type,
            "run_id": run_id,
            "draft_only": draft_only,
            "timestamp": datetime.utcnow().isoformat(),
        })
        self.workflow_run_ids.append(run_id)

    def add_mcp_call(
        self,
        tool: str,
        call_id: str,
        allowed: bool,
    ) -> None:
        self.mcp_calls.append({
            "tool": tool,
            "call_id": call_id,
            "allowed": allowed,
            "timestamp": datetime.utcnow().isoformat(),
        })
        self.mcp_call_ids.append(call_id)

    def add_request_id(self, request_id: str) -> None:
        self.request_ids.append(request_id)

    def add_correlation_id(self, correlation_id: str) -> None:
        self.correlation_ids.append(correlation_id)

    def add_audit_event(self, event_id: str) -> None:
        self.audit_event_ids.append(event_id)

    def add_security_event(self, event_id: str) -> None:
        self.security_event_ids.append(event_id)

    def add_limitation(self, limitation: str) -> None:
        self.limitations.append(limitation)

    def add_artifact(self, path: str) -> None:
        self.artifacts.append(path)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "test_run_id": self.test_run_id,
            "phase": self.phase,
            "mode": self.mode,
            "component": self.component,
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "command": self.command,
            "endpoint": self.endpoint,
            "method": self.method,
            "backend_running": self.backend_running,
            "frontend_running": self.frontend_running,
            "browser_used": self.browser_used,
            "api_calls": self.api_calls,
            "ui_actions": self.ui_actions,
            "workflow_runs": self.workflow_runs,
            "mcp_calls": self.mcp_calls,
            "service_calls": self.service_calls,
            "request_ids": self.request_ids,
            "correlation_ids": self.correlation_ids,
            "workflow_run_ids": self.workflow_run_ids,
            "mcp_call_ids": self.mcp_call_ids,
            "audit_event_ids": self.audit_event_ids,
            "security_event_ids": self.security_event_ids,
            "production_ready": self.production_ready,
            "live_provider_flags": self.live_provider_flags,
            "no_live_payment_mode": self.no_live_payment_mode,
            "kill_switch_status": self.kill_switch_status,
            "result": self.result,
            "confidence_impact": self.confidence_impact,
            "limitations": self.limitations,
            "artifacts": self.artifacts,
        }

    def contains_forbidden_content(self) -> list[str]:
        """Check if evidence contains forbidden content.

        Returns:
            List of violations (empty if safe).
        """
        violations: list[str] = []
        serialized = str(self.to_dict())

        forbidden_patterns = [
            ".env",
            "sk_live_",
            "rk_live_",
            "Authorization",
            "Set-Cookie",
            "-----BEGIN",
            "ghp_",
            "gho_",
            "ghu_",
            "ghs_",
            "ghr_",
        ]

        for pattern in forbidden_patterns:
            if pattern.lower() in serialized.lower():
                violations.append(f"Contains forbidden pattern: {pattern}")

        return violations


# ── Evidence Collector ────────────────────────────────────────────────────


class RuntimeEvidenceCollector:
    """Collects and manages runtime evidence across scenarios."""

    def __init__(self) -> None:
        self.evidence_list: list[RuntimeEvidence] = []
        self._run_id: str = f"run_{uuid.uuid4().hex[:12]}"

    @property
    def run_id(self) -> str:
        return self._run_id

    def create_evidence(
        self,
        component: str,
        scenario_id: str,
        scenario_name: str,
        mode: str = "TEST_HARNESS",
    ) -> RuntimeEvidence:
        ev = RuntimeEvidence(
            test_run_id=self._run_id,
            component=component,
            scenario_id=scenario_id,
            scenario_name=scenario_name,
            mode=mode,
        )
        self.evidence_list.append(ev)
        return ev

    def get_by_component(self, component: str) -> list[RuntimeEvidence]:
        return [ev for ev in self.evidence_list if ev.component == component]

    def get_results_summary(self) -> dict[str, Any]:
        total = len(self.evidence_list)
        passed = sum(1 for ev in self.evidence_list if ev.result == "PASS")
        failed = sum(1 for ev in self.evidence_list if ev.result == "FAIL")
        blocked = sum(1 for ev in self.evidence_list if ev.result == "BLOCKED")
        partial = sum(1 for ev in self.evidence_list if ev.result == "PARTIAL")
        not_tested = sum(1 for ev in self.evidence_list if ev.result == "NOT_TESTED")
        flaky = sum(1 for ev in self.evidence_list if ev.result == "FLAKY_PASS")

        return {
            "run_id": self._run_id,
            "total": total,
            "passed": passed,
            "failed": failed,
            "blocked": blocked,
            "partial": partial,
            "not_tested": not_tested,
            "flaky_pass": flaky,
            "evidence_ids": [ev.evidence_id for ev in self.evidence_list],
        }

    def has_forbidden_content(self) -> list[dict[str, Any]]:
        violations: list[dict[str, Any]] = []
        for ev in self.evidence_list:
            ev_violations = ev.contains_forbidden_content()
            if ev_violations:
                violations.append({
                    "evidence_id": ev.evidence_id,
                    "violations": ev_violations,
                })
        return violations

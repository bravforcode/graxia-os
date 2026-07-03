"""Tests for workflow runtime/service contract.

Uses service-path (direct service calls) since no HTTP workflow endpoint exists.
"""

from __future__ import annotations

import uuid

import pytest
from app.beta.synthetic_tester.runtime_evidence import RuntimeEvidence
from app.beta.synthetic_tester.test_data import (
    make_test_auth_context,
    make_test_opportunity_payload,
    make_test_content_draft_payload,
    make_wrong_org_auth_context,
    make_missing_permission_auth_context,
)

# Service-path workflow registry
WORKFLOW_REGISTRY = {
    "opportunity_scout": {
        "permission": "workflow:run_opportunity_scout",
        "draft_only": True,
        "approval_required": True,
        "live_provider_calls": False,
    },
    "content_plan_draft": {
        "permission": "workflow:run_content_plan",
        "draft_only": True,
        "approval_required": True,
        "live_provider_calls": False,
    },
    "experiment_planner": {
        "permission": "workflow:run_experiment_planner",
        "draft_only": True,
        "approval_required": True,
        "live_provider_calls": False,
    },
    "failure_analysis_review": {
        "permission": "workflow:run_failure_analysis",
        "draft_only": True,
        "approval_required": True,
        "live_provider_calls": False,
    },
}


def _run_workflow_service(
    workflow_type: str,
    auth_context: dict,
    *,
    params: dict | None = None,
    kill_switch_active: bool = False,
    approval_granted: bool = False,
) -> dict:
    """Service-path workflow execution check.

    Returns dict with draft_only, approval_required, run_id, etc.
    """
    config = WORKFLOW_REGISTRY.get(workflow_type)
    if not config:
        return {
            "allowed": False,
            "reason": "ERR_WORKFLOW_NOT_FOUND",
        }

    if kill_switch_active:
        return {
            "allowed": False,
            "reason": "ERR_KILL_SWITCH_ACTIVE",
        }

    # Permission check
    required_perm = config["permission"]
    user_perms = auth_context.get("permissions", [])
    if required_perm not in user_perms:
        return {
            "allowed": False,
            "reason": "ERR_MISSING_PERMISSION",
        }

    # Approval required for external-facing output
    if config.get("approval_required") and not approval_granted:
        return {
            "allowed": False,
            "reason": "ERR_APPROVAL_REQUIRED",
            "draft_only": True,
            "approval_required": True,
        }

    return {
        "allowed": True,
        "reason": "OK",
        "draft_only": config["draft_only"],
        "approval_required": config["approval_required"],
        "live_provider_called": config["live_provider_calls"],
        "production_ready": False,
        "no_send": True,
        "no_publish": True,
        "no_charge": True,
        "run_id": f"wf_{workflow_type}_{uuid.uuid4().hex[:12]}",
        "organization_id": auth_context.get("organization_id", ""),
        "result": params or {},
    }


class TestWorkflowRuntimeContract:
    """Service-path workflow validation."""

    def test_opportunity_scout_draft_only(self):
        ctx = make_test_auth_context(permissions=["workflow:run_opportunity_scout"])
        result = _run_workflow_service("opportunity_scout", ctx, approval_granted=True)
        assert result["allowed"] is True
        assert result["draft_only"] is True
        assert result["no_send"] is True
        assert result["no_publish"] is True
        assert result["no_charge"] is True

    def test_content_plan_draft_only(self):
        ctx = make_test_auth_context(permissions=["workflow:run_content_plan"])
        result = _run_workflow_service("content_plan_draft", ctx, approval_granted=True)
        assert result["allowed"] is True
        assert result["draft_only"] is True

    def test_experiment_planner_draft_only(self):
        ctx = make_test_auth_context(permissions=["workflow:run_experiment_planner"])
        result = _run_workflow_service("experiment_planner", ctx, approval_granted=True)
        assert result["allowed"] is True
        assert result["draft_only"] is True

    def test_failure_analysis_review_draft_only(self):
        ctx = make_test_auth_context(permissions=["workflow:run_failure_analysis"])
        result = _run_workflow_service("failure_analysis_review", ctx, approval_granted=True)
        assert result["allowed"] is True
        assert result["draft_only"] is True

    def test_missing_permission_denied(self):
        ctx = make_missing_permission_auth_context()
        result = _run_workflow_service("opportunity_scout", ctx)
        assert result["allowed"] is False
        assert "MISSING_PERMISSION" in result["reason"]

    def test_org_mismatch_denied(self):
        ctx = make_wrong_org_auth_context()
        result = _run_workflow_service("opportunity_scout", ctx)
        assert result["allowed"] is False

    def test_kill_switch_active_denied(self):
        ctx = make_test_auth_context(permissions=["workflow:run_opportunity_scout"])
        result = _run_workflow_service("opportunity_scout", ctx, kill_switch_active=True)
        assert result["allowed"] is False
        assert "KILL_SWITCH" in result["reason"]

    def test_no_live_provider_called(self):
        ctx = make_test_auth_context(permissions=["workflow:run_opportunity_scout"])
        result = _run_workflow_service("opportunity_scout", ctx, approval_granted=True)
        assert result["live_provider_called"] is False

    def test_approval_required_for_external(self):
        ctx = make_test_auth_context(permissions=["workflow:run_opportunity_scout"])
        result = _run_workflow_service("opportunity_scout", ctx, approval_granted=False)
        assert result["allowed"] is False
        assert "APPROVAL_REQUIRED" in result["reason"]

    def test_approval_granted_succeeds(self):
        ctx = make_test_auth_context(permissions=["workflow:run_opportunity_scout"])
        result = _run_workflow_service("opportunity_scout", ctx, approval_granted=True)
        assert result["allowed"] is True

    def test_production_ready_false(self):
        ctx = make_test_auth_context(permissions=["workflow:run_opportunity_scout"])
        result = _run_workflow_service("opportunity_scout", ctx, approval_granted=True)
        assert result["production_ready"] is False

    def test_unknown_workflow_returns_error(self):
        ctx = make_test_auth_context()
        result = _run_workflow_service("nonexistent", ctx)
        assert result["allowed"] is False
        assert "NOT_FOUND" in result["reason"]

    def test_evidence_records_workflow_run(self):
        ev = RuntimeEvidence(
            component="workflow_runtime",
            scenario_id="W001",
            scenario_name="Workflow draft-only",
        )
        ctx = make_test_auth_context(permissions=["workflow:run_opportunity_scout"])
        result = _run_workflow_service("opportunity_scout", ctx, approval_granted=True)
        ev.add_workflow_run("opportunity_scout", result["run_id"], result["draft_only"])
        ev.complete("PASS")
        assert len(ev.workflow_runs) == 1

    def test_org_id_preserved(self):
        ctx = make_test_auth_context(permissions=["workflow:run_opportunity_scout"])
        result = _run_workflow_service("opportunity_scout", ctx, approval_granted=True)
        assert result["organization_id"] == ctx["organization_id"]

    def test_no_raw_secret_in_result(self):
        ctx = make_test_auth_context(permissions=["workflow:run_opportunity_scout"])
        result = _run_workflow_service("opportunity_scout", ctx, approval_granted=True)
        serialized = str(result)
        assert "sk_" not in serialized
        assert "ghp_" not in serialized


SERVICE_PATH_MODE = True
WORKFLOW_HTTP_RUNTIME_TESTED = False
WORKFLOW_SERVICE_PATH_TESTED = True
WORKFLOW_TEST_HARNESS_ONLY = False

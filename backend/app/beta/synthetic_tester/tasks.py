"""Synthetic test task library for AI Tester Lab.

30 tasks across 11 categories, each with required mode, persona mappings,
evidence requirements, and hard-fail conditions.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SyntheticTask:
    """A single synthetic test task."""

    task_id: str
    title: str
    category: str
    required_mode: str
    persona_ids: list[str]
    setup: dict
    steps: list[str]
    expected_result: str
    evidence_required: list[str]
    hard_fail_conditions: list[str]
    confidence_impact: dict


# ── Task Definitions ──────────────────────────────────────────────────────────

T001 = SyntheticTask(
    task_id="T001",
    title="Understand Beta Limits",
    category="ONBOARDING",
    required_mode="STATIC_REVIEW",
    persona_ids=["P01", "P02", "P05", "P09", "P10"],
    setup={},
    steps=[
        "Read beta launch policy",
        "Read beta session script",
        "Identify what is NOT allowed (send, publish, charge)",
        "Explain beta limits in own words",
    ],
    expected_result="User can correctly identify all prohibited actions",
    evidence_required=["policy_reviewed", "limits_identified"],
    hard_fail_conditions=["thinks sending is allowed", "thinks payment is active"],
    confidence_impact={"synthetic_beta_confidence": 5},
)

T002 = SyntheticTask(
    task_id="T002",
    title="Find Safety Status",
    category="SAFETY_UNDERSTANDING",
    required_mode="STATIC_REVIEW",
    persona_ids=["P01", "P02", "P04", "P05", "P10"],
    setup={},
    steps=[
        "Find production readiness status",
        "Find live provider status",
        "Find kill switch status",
        "Explain what each means",
    ],
    expected_result="User can locate and interpret all safety status indicators",
    evidence_required=["safety_status_found", "status_interpreted_correctly"],
    hard_fail_conditions=["cannot find production status", "misunderstands kill switch"],
    confidence_impact={"synthetic_beta_confidence": 5, "safety_confidence": 5},
)

T003 = SyntheticTask(
    task_id="T003",
    title="Verify Production False",
    category="READINESS",
    required_mode="STATIC_REVIEW",
    persona_ids=["P01", "P04", "P05"],
    setup={},
    steps=[
        "Check PRODUCTION_READY value",
        "Check ALLOW_PRODUCTION_DB value",
        "Check ALLOW_LIVE_STRIPE value",
        "Confirm all are false",
    ],
    expected_result="PRODUCTION_READY and all live provider flags are false",
    evidence_required=["production_ready_false", "live_providers_false"],
    hard_fail_conditions=["production_ready_true", "live_provider_true"],
    confidence_impact={"synthetic_beta_confidence": 5, "security_confidence": 10},
)

T004 = SyntheticTask(
    task_id="T004",
    title="Verify Live Providers False",
    category="READINESS",
    required_mode="STATIC_REVIEW",
    persona_ids=["P01", "P04", "P07"],
    setup={},
    steps=[
        "Check ALLOW_REAL_EMAIL_SEND",
        "Check ALLOW_REAL_GOOGLE_MUTATION",
        "Check ALLOW_REAL_LLM_CALLS",
        "Check NO_LIVE_PAYMENT_MODE",
        "Confirm all are false/locked",
    ],
    expected_result="All live provider flags are disabled/locked",
    evidence_required=["live_providers_false"],
    hard_fail_conditions=["any live provider flag true"],
    confidence_impact={"security_confidence": 10},
)

T005 = SyntheticTask(
    task_id="T005",
    title="Run Opportunity Scout Draft",
    category="WORKFLOW",
    required_mode="TEST_HARNESS",
    persona_ids=["P01", "P03", "P07", "P10", "P12"],
    setup={"workflow": "opportunity_scout", "mode": "draft"},
    steps=[
        "Initiate opportunity_scout workflow",
        "Provide test input",
        "Review generated draft",
        "Verify output is draft-only (no send)",
        "Verify output has request_id",
    ],
    expected_result="Draft produced with request_id, no send/publish/charge occurred",
    evidence_required=["draft_produced", "request_id_present", "no_auto_send"],
    hard_fail_conditions=["auto_send_occurred", "no_request_id", "workflow_failed"],
    confidence_impact={"workflow_confidence": 10},
)

T006 = SyntheticTask(
    task_id="T006",
    title="Run Content Plan Draft",
    category="WORKFLOW",
    required_mode="TEST_HARNESS",
    persona_ids=["P02", "P03"],
    setup={"workflow": "content_plan_draft", "mode": "draft"},
    steps=[
        "Initiate content_plan draft",
        "Provide test input",
        "Review generated content plan",
        "Verify output is draft-only",
        "Verify output has request_id",
    ],
    expected_result="Content plan draft produced with request_id, no auto-publish",
    evidence_required=["draft_produced", "request_id_present", "no_auto_publish"],
    hard_fail_conditions=["auto_publish_occurred", "no_request_id"],
    confidence_impact={"workflow_confidence": 10},
)

T007 = SyntheticTask(
    task_id="T007",
    title="Run Experiment Planner",
    category="WORKFLOW",
    required_mode="TEST_HARNESS",
    persona_ids=["P03"],
    setup={"workflow": "experiment_planner", "mode": "draft"},
    steps=[
        "Initiate experiment_planner workflow",
        "Provide test input",
        "Review generated experiment plan",
        "Verify output is draft-only",
    ],
    expected_result="Experiment plan draft produced, no unauthorized action",
    evidence_required=["draft_produced"],
    hard_fail_conditions=["auto_execute_occurred"],
    confidence_impact={"workflow_confidence": 5},
)

T008 = SyntheticTask(
    task_id="T008",
    title="Run Failure Analysis Review",
    category="WORKFLOW",
    required_mode="TEST_HARNESS",
    persona_ids=["P03"],
    setup={"workflow": "failure_analysis_review", "mode": "draft"},
    steps=[
        "Initiate failure_analysis_review workflow",
        "Provide test input",
        "Review generated analysis",
        "Verify output is draft-only",
    ],
    expected_result="Failure analysis draft produced, no unauthorized action",
    evidence_required=["draft_produced"],
    hard_fail_conditions=["auto_execute_occurred"],
    confidence_impact={"workflow_confidence": 5},
)

T009 = SyntheticTask(
    task_id="T009",
    title="Review Draft and Choose Do/Skip/Delay",
    category="APPROVAL",
    required_mode="TEST_HARNESS",
    persona_ids=["P01", "P02", "P03", "P05", "P07", "P10", "P12"],
    setup={"workflow": "any", "mode": "approval"},
    steps=[
        "Receive draft output",
        "Review draft content",
        "Choose Do (approve), Skip (reject), or Delay",
        "Verify decision is logged",
    ],
    expected_result="User can choose do/skip/delay, decision is recorded",
    evidence_required=["decision_made", "decision_logged", "no_auto_send"],
    hard_fail_conditions=["cannot choose", "decision not logged"],
    confidence_impact={"operator_confidence": 10},
)

T010 = SyntheticTask(
    task_id="T010",
    title="Reject Unsafe Draft",
    category="APPROVAL",
    required_mode="TEST_HARNESS",
    persona_ids=["P02", "P04", "P11"],
    setup={"workflow": "any", "mode": "approval", "draft_type": "unsafe"},
    steps=[
        "Receive draft that looks unsafe",
        "Choose Skip (reject)",
        "Verify draft is NOT sent",
        "Verify rejection is logged",
    ],
    expected_result="Unsafe draft is rejected, no send/publish occurs, rejection logged",
    evidence_required=["rejection_logged", "no_send", "no_publish"],
    hard_fail_conditions=["draft_sent_after_reject", "rejection_not_logged"],
    confidence_impact={"safety_confidence": 10, "operator_confidence": 10},
)

T011 = SyntheticTask(
    task_id="T011",
    title="Verify Dangerous Tool Blocked",
    category="ADVERSARIAL",
    required_mode="ADVERSARIAL_SECURITY",
    persona_ids=["P02", "P04", "P07"],
    setup={"tool": "dangerous", "mode": "block_check"},
    steps=[
        "Attempt to call dangerous MCP tool",
        "Attempt to send email",
        "Attempt to charge payment",
        "Attempt to publish content",
        "Verify all are blocked with safe error",
    ],
    expected_result="All dangerous actions blocked with clear safe errors",
    evidence_required=["blocked_with_safe_error", "no_side_effect"],
    hard_fail_conditions=["any dangerous action succeeded", "no error returned"],
    confidence_impact={"safety_confidence": 15, "security_confidence": 15},
)

T012 = SyntheticTask(
    task_id="T012",
    title="Submit Confusion Feedback",
    category="FEEDBACK",
    required_mode="STATIC_REVIEW",
    persona_ids=["P01", "P05", "P09", "P10", "P12"],
    setup={"feedback_type": "confusion"},
    steps=[
        "Identify something confusing",
        "Submit feedback about confusion",
        "Verify feedback received without error",
    ],
    expected_result="Feedback submitted successfully, no crash, no data leak",
    evidence_required=["feedback_submitted", "no_error"],
    hard_fail_conditions=["feedback_crashed", "secrets_in_feedback_response"],
    confidence_impact={"synthetic_beta_confidence": 3},
)

T013 = SyntheticTask(
    task_id="T013",
    title="Submit Safety Feedback",
    category="FEEDBACK",
    required_mode="STATIC_REVIEW",
    persona_ids=["P04", "P09"],
    setup={"feedback_type": "safety_concern"},
    steps=[
        "Submit a safety concern via feedback",
        "Verify feedback is received",
        "Verify no sensitive data exposed",
    ],
    expected_result="Safety feedback accepted without sensitive data leak",
    evidence_required=["feedback_submitted", "no_secret_leak"],
    hard_fail_conditions=["secret_leaked", "feedback_rejected"],
    confidence_impact={"safety_confidence": 5},
)

T014 = SyntheticTask(
    task_id="T014",
    title="Try Cross-Org MCP Call",
    category="ADVERSARIAL",
    required_mode="ADVERSARIAL_SECURITY",
    persona_ids=["P04", "P06"],
    setup={"attack": "cross_org_mcp"},
    steps=[
        "Attempt MCP call with mismatched organization_id",
        "Verify ERR_ORG_MISMATCH returned",
        "Verify security audit event emitted",
    ],
    expected_result="Cross-org MCP call denied, audit event emitted",
    evidence_required=["denied", "security_event_emitted"],
    hard_fail_conditions=["call_succeeded", "no_audit_event"],
    confidence_impact={"security_confidence": 15},
)

T015 = SyntheticTask(
    task_id="T015",
    title="Try Cross-Org Workflow Run",
    category="ADVERSARIAL",
    required_mode="ADVERSARIAL_SECURITY",
    persona_ids=["P04", "P06"],
    setup={"attack": "cross_org_workflow"},
    steps=[
        "Attempt workflow run with mismatched organization_id",
        "Verify ERR_ORG_MISMATCH returned",
        "Verify security audit event emitted",
    ],
    expected_result="Cross-org workflow denied, audit event emitted",
    evidence_required=["denied", "security_event_emitted"],
    hard_fail_conditions=["workflow_executed_for_wrong_org", "no_audit_event"],
    confidence_impact={"security_confidence": 15},
)

T016 = SyntheticTask(
    task_id="T016",
    title="Try Missing Permission Workflow",
    category="ADVERSARIAL",
    required_mode="ADVERSARIAL_SECURITY",
    persona_ids=["P04", "P06"],
    setup={"attack": "missing_permission"},
    steps=[
        "Attempt workflow without required permission",
        "Verify ERR_PERMISSION_DENIED returned",
        "Verify audit event emitted",
    ],
    expected_result="Missing permission workflow denied with safe error",
    evidence_required=["denied", "security_event_emitted"],
    hard_fail_conditions=["workflow_executed_without_permission", "no_audit_event"],
    confidence_impact={"security_confidence": 15},
)

T017 = SyntheticTask(
    task_id="T017",
    title="Try Kill Switch Bypass",
    category="ADVERSARIAL",
    required_mode="ADVERSARIAL_SECURITY",
    persona_ids=["P04", "P06"],
    setup={"attack": "kill_switch_bypass"},
    steps=[
        "Attempt to disable kill switch without permission",
        "Attempt workflow while kill switch active",
        "Verify both attempts are denied",
    ],
    expected_result="Kill switch cannot be bypassed, operations blocked when active",
    evidence_required=["bypass_denied", "operations_blocked"],
    hard_fail_conditions=["kill_switch_disabled", "workflow_running_while_killed"],
    confidence_impact={"security_confidence": 20},
)

T018 = SyntheticTask(
    task_id="T018",
    title="Try Live Payment Flag",
    category="ADVERSARIAL",
    required_mode="ADVERSARIAL_SECURITY",
    persona_ids=["P06", "P07"],
    setup={"attack": "enable_live_payment"},
    steps=[
        "Attempt to enable ALLOW_LIVE_STRIPE",
        "Attempt to disable NO_LIVE_PAYMENT_MODE",
        "Verify both are blocked",
    ],
    expected_result="Live payment flags cannot be enabled by unprivileged user",
    evidence_required=["blocked", "no_payment_flag_change"],
    hard_fail_conditions=["live_payment_enabled", "no_live_payment_disabled"],
    confidence_impact={"security_confidence": 20},
)

T019 = SyntheticTask(
    task_id="T019",
    title="Try Auto-Send",
    category="ADVERSARIAL",
    required_mode="ADVERSARIAL_SECURITY",
    persona_ids=["P04", "P06", "P07"],
    setup={"attack": "auto_send"},
    steps=[
        "Attempt to send email without approval",
        "Attempt to craft workflow that auto-sends",
        "Verify all blocked",
    ],
    expected_result="Auto-send impossible, approval always required",
    evidence_required=["blocked", "approval_required"],
    hard_fail_conditions=["email_sent_without_approval"],
    confidence_impact={"security_confidence": 20},
)

T020 = SyntheticTask(
    task_id="T020",
    title="Try Auto-Publish",
    category="ADVERSARIAL",
    required_mode="ADVERSARIAL_SECURITY",
    persona_ids=["P04", "P06", "P07"],
    setup={"attack": "auto_publish"},
    steps=[
        "Attempt to publish content without approval",
        "Attempt to craft workflow that auto-publishes",
        "Verify all blocked",
    ],
    expected_result="Auto-publish impossible, approval always required",
    evidence_required=["blocked", "approval_required"],
    hard_fail_conditions=["content_published_without_approval"],
    confidence_impact={"security_confidence": 20},
)

T021 = SyntheticTask(
    task_id="T021",
    title="Try Prompt Injection in Feedback",
    category="ADVERSARIAL",
    required_mode="ADVERSARIAL_SECURITY",
    persona_ids=["P06"],
    setup={"attack": "prompt_injection", "vector": "feedback"},
    steps=[
        "Submit feedback containing prompt injection attempt",
        "Verify system does not execute injected prompt",
        "Verify no side effect",
    ],
    expected_result="Prompt injection in feedback does not execute",
    evidence_required=["blocked", "no_side_effect"],
    hard_fail_conditions=["injection_succeeded", "side_effect_occurred"],
    confidence_impact={"security_confidence": 10},
)

T022 = SyntheticTask(
    task_id="T022",
    title="Try Oversized Feedback",
    category="ADVERSARIAL",
    required_mode="ADVERSARIAL_SECURITY",
    persona_ids=["P06", "P09", "P12"],
    setup={"attack": "oversized_payload"},
    steps=[
        "Submit extremely long feedback",
        "Submit feedback with special characters",
        "Verify safe error returned, no crash",
    ],
    expected_result="Oversized/special-char feedback produces safe error, no crash",
    evidence_required=["safe_error_returned", "no_crash"],
    hard_fail_conditions=["crash", "unhandled_exception"],
    confidence_impact={"safety_confidence": 5},
)

T023 = SyntheticTask(
    task_id="T023",
    title="Check Keyboard Navigation",
    category="ACCESSIBILITY",
    required_mode="STATIC_REVIEW",
    persona_ids=["P05"],
    setup={"check": "keyboard_navigation"},
    steps=[
        "Review UI for keyboard-accessible elements",
        "Check focus visibility",
        "Check label associations",
        "Check heading hierarchy",
    ],
    expected_result="Baseline keyboard accessibility observed or documented gaps",
    evidence_required=["keyboard_reviewed", "gaps_documented"],
    hard_fail_conditions=[],
    confidence_impact={"accessibility_confidence": 5},
)

T024 = SyntheticTask(
    task_id="T024",
    title="Check Error Message Clarity",
    category="ACCESSIBILITY",
    required_mode="STATIC_REVIEW",
    persona_ids=["P05", "P12"],
    setup={"check": "error_messages"},
    steps=[
        "Review safe error templates",
        "Check if error messages are clear and actionable",
        "Check if error messages expose internals",
    ],
    expected_result="Error messages are clear, safe, and actionable",
    evidence_required=["errors_reviewed", "no_internal_exposure"],
    hard_fail_conditions=["error_exposes_stack_trace", "error_exposes_internals"],
    confidence_impact={"accessibility_confidence": 5, "safety_confidence": 5},
)

T025 = SyntheticTask(
    task_id="T025",
    title="Verify Request Correlation",
    category="OPERATOR",
    required_mode="TEST_HARNESS",
    persona_ids=["P02", "P03", "P08", "P11"],
    setup={"check": "correlation"},
    steps=[
        "Execute a workflow",
        "Capture request_id from output",
        "Capture correlation_id",
        "Verify they are present and non-empty",
    ],
    expected_result="request_id and correlation_id present in workflow output",
    evidence_required=["request_id_present", "correlation_id_present"],
    hard_fail_conditions=["no_request_id", "no_correlation_id"],
    confidence_impact={"operator_confidence": 10, "evidence_quality": 10},
)

T026 = SyntheticTask(
    task_id="T026",
    title="Verify Audit Event",
    category="OPERATOR",
    required_mode="TEST_HARNESS",
    persona_ids=["P02", "P08", "P11"],
    setup={"check": "audit_event"},
    steps=[
        "Execute an action that should emit audit event",
        "Verify audit event was emitted",
        "Verify audit event contains required fields",
    ],
    expected_result="Audit event emitted with required fields",
    evidence_required=["audit_event_emitted"],
    hard_fail_conditions=["no_audit_event"],
    confidence_impact={"operator_confidence": 10, "evidence_quality": 10},
)

T027 = SyntheticTask(
    task_id="T027",
    title="Run Operator Daily Checklist",
    category="OPERATOR",
    required_mode="STATIC_REVIEW",
    persona_ids=["P02", "P11"],
    setup={"checklist": "daily_operator"},
    steps=[
        "Review operator daily checklist",
        "Verify each item is actionable",
        "Verify checklist covers safety checks",
    ],
    expected_result="Daily checklist covers all required operator tasks",
    evidence_required=["checklist_reviewed", "gaps_documented"],
    hard_fail_conditions=["safety_check_missing_from_checklist"],
    confidence_impact={"operator_confidence": 10},
)

T028 = SyntheticTask(
    task_id="T028",
    title="Run Kill Switch Drill",
    category="OPERATOR",
    required_mode="TEST_HARNESS",
    persona_ids=["P02", "P11"],
    setup={"drill": "kill_switch"},
    steps=[
        "Activate kill switch",
        "Verify beta operations blocked",
        "Deactivate kill switch",
        "Verify beta operations restored",
    ],
    expected_result="Kill switch toggles correctly, blocks/restores operations",
    evidence_required=["kill_switch_blocks", "kill_switch_restores"],
    hard_fail_conditions=["kill_switch_does_not_block", "cannot_restore"],
    confidence_impact={"safety_confidence": 15, "operator_confidence": 10},
)

T029 = SyntheticTask(
    task_id="T029",
    title="Verify No Raw Token in Evidence",
    category="ADVERSARIAL",
    required_mode="ADVERSARIAL_SECURITY",
    persona_ids=["P04", "P06", "P08", "P09"],
    setup={"check": "no_raw_token"},
    steps=[
        "Capture output from workflows, feedback, and errors",
        "Search for patterns matching tokens, secrets, keys",
        "Verify no raw credentials exposed",
    ],
    expected_result="No raw tokens, secrets, or credentials in any output",
    evidence_required=["no_token_leak"],
    hard_fail_conditions=["raw_token_found", "secret_exposed"],
    confidence_impact={"security_confidence": 15, "safety_confidence": 10},
)

T030 = SyntheticTask(
    task_id="T030",
    title="Produce Fix Recommendation",
    category="OPERATOR",
    required_mode="STATIC_REVIEW",
    persona_ids=["P08", "P11"],
    setup={"task": "fix_recommendation"},
    steps=[
        "Review all findings from other tasks",
        "Classify findings by severity (S0-S4)",
        "Produce prioritized fix recommendations",
    ],
    expected_result="Prioritized fix recommendations produced from evidence",
    evidence_required=["fix_recommendations_produced"],
    hard_fail_conditions=[],
    confidence_impact={"synthetic_beta_confidence": 5},
)

# ── Registry ──────────────────────────────────────────────────────────────────

TASKS: dict[str, SyntheticTask] = {
    t.task_id: t
    for t in [
        T001, T002, T003, T004, T005,
        T006, T007, T008, T009, T010,
        T011, T012, T013, T014, T015,
        T016, T017, T018, T019, T020,
        T021, T022, T023, T024, T025,
        T026, T027, T028, T029, T030,
    ]
}


def get_task(task_id: str) -> SyntheticTask | None:
    """Get a task by ID."""
    return TASKS.get(task_id)


def list_tasks() -> list[SyntheticTask]:
    """List all tasks."""
    return list(TASKS.values())


def list_tasks_by_category(category: str) -> list[SyntheticTask]:
    """List tasks in a given category."""
    return [t for t in TASKS.values() if t.category == category]


def list_tasks_by_mode(mode: str) -> list[SyntheticTask]:
    """List tasks requiring a given mode."""
    return [t for t in TASKS.values() if t.required_mode == mode]

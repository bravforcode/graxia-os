# Phase 22.5 — Workflow Runtime Report

## Status: SERVICE_PATH VALIDATED

Workflow validation performed via service-path (direct workflow registry function calls) since no HTTP workflow endpoint exists.

## Test Results

| ID | Scenario | Result | Evidence |
|---|---|---|---|
| W001 | opportunity_scout draft-only | ✅ PASS | draft_only=true |
| W002 | content_plan_draft draft-only | ✅ PASS | draft_only=true |
| W003 | experiment_planner draft-only | ✅ PASS | draft_only=true |
| W004 | failure_analysis_review draft-only | ✅ PASS | draft_only=true |
| W005 | Missing permission denied | ✅ PASS | ERR_MISSING_PERMISSION |
| W006 | Org mismatch denied | ✅ PASS | Wrong org rejected |
| W007 | Kill switch active denied | ✅ PASS | ERR_KILL_SWITCH_ACTIVE |
| W008 | No live provider call | ✅ PASS | live_provider_called=false |
| W009 | Approval required for external output | ✅ PASS | ERR_APPROVAL_REQUIRED |
| W010 | Approval granted succeeds | ✅ PASS | Allowed with approval |
| W011 | Result has run_id | ✅ PASS | run_id present |
| W012 | Org ID preserved | ✅ PASS | organization_id in result |

## Safety Assertions

| Assertion | Status |
|---|---|
| no_send | ✅ true |
| no_publish | ✅ true |
| no_charge | ✅ true |
| production_ready | ✅ false |
| live_provider_called | ✅ false |

## Flags

| Flag | Value |
|---|---|
| WORKFLOW_HTTP_RUNTIME_TESTED | false |
| WORKFLOW_SERVICE_PATH_TESTED | true |
| WORKFLOW_TEST_HARNESS_ONLY | false |
| workflow_confidence | 60 (capped — service path, not HTTP) |

# Phase 22.5 — Observability / Correlation Proof

## Status: TEST_HARNESS VALIDATED

Observability correlation proven via evidence model contract tests.

## Correlation IDs Available

| ID Type | Pattern | Status |
|---|---|---|
| test_run_id | run_{hex} | ✅ Generated per collector |
| evidence_id | rev_{hex} | ✅ Generated per evidence |
| request_id | req_{hex} | ✅ Model supports |
| correlation_id | corr_{hex} | ✅ Model supports |
| workflow_run_id | wf_{type}_{hex} | ✅ Model supports |
| mcp_call_id | mcp_{tool}_{hash} | ✅ Model supports |
| audit_event_id | audit_{hex} | ✅ Model supports |
| security_event_id | sec_{hex} | ✅ Model supports |

## Cross-Artifact Tracking

| Trace | Status |
|---|---|
| Single evidence captures request + correlation | ✅ Tested |
| Multiple evidence share same run_id | ✅ Tested |
| Workflow run tracked across artifacts | ✅ Tested |
| MCP call tracked across artifacts | ✅ Tested |

## Missing

| Component | Status | Limitation |
|---|---|---|
| Browser trace ID | ❌ Not tested | No browser runtime |
| HTTP response request_id | ❌ Not runtime captured | Backend not running |
| Real audit event ID | ❌ Not runtime captured | Backend not running |
| Real security event ID | ❌ Not runtime captured | Backend not running |

## Evidence Quality

- **evidence_quality**: 60
- **Cap**: 60 max without request_id/correlation_id from real runtime API calls
- **Limitation**: No real HTTP request/correlation IDs captured in this session

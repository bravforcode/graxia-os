# Tool Permission Audit Report

**Generated:** 2026-05-02
**Status:** PRE-DEPLOYMENT SECURITY AUDIT

## Executive Summary

| Risk Level | Count | Status |
|------------|-------|--------|
| CRITICAL | 4 | Needs enforcement |
| HIGH | 2 | Needs enforcement |
| MEDIUM | 0 | OK |
| LOW | 4 | OK |

## High-Risk Execution Paths

| # | Action | Current File | Enforced? | Bypass Risk | Evidence |
|---|--------|--------------|-----------|-------------|----------|
| 1 | `email_send` | `app/core/approval_flow.py:_execute_email_send()` | ✅ YES | LOW | Called only after approval granted |
| 2 | `linkedin_outreach` | `app/core/approval_flow.py:_execute_linkedin_outreach()` | ✅ YES | LOW | Called only after approval granted |
| 3 | `job_apply` | `app/core/approval_flow.py:_execute_job_apply()` | ✅ YES | LOW | Called only after approval granted |
| 4 | `send_email` | `app/agents/business/email_agent.py:send_email()` | ⚠️ PARAMETER | **HIGH** | `require_approval: bool = True` can be bypassed |
| 5 | `send_email` | `app/agents/outreach_agent.py:run()` | ⚠️ CONFIG | **HIGH** | `OUTREACH_AUTOSEND_ENABLED` can bypass approval |
| 6 | `scrape_linkedin` | `app/core/approval_flow.py:_execute_linkedin_outreach()` | ✅ YES | LOW | Called only after approval granted |

## Critical Findings

### Finding 1: Email Agent Bypass Risk

**File:** `app/agents/business/email_agent.py:157-196`

```python
async def send_email(
    self,
    to: str,
    subject: str,
    body: str,
    cc: Optional[List[str]] = None,
    require_approval: bool = True  # <-- PARAMETER CONTROLLED
) -> Dict[str, Any]:
```

**Risk:** Agent can bypass approval by calling `send_email(require_approval=False)`

**Fix Required:** Add mandatory ToolPermissionPolicy check before any email send.

### Finding 2: Outreach Agent Bypass Risk

**File:** `app/agents/outreach_agent.py:202-249`

```python
if not settings.OUTREACH_AUTOSEND_ENABLED:
    await queue_approval_request(...)  # Safe path
else:
    message_id = await google_workspace.send_message(...)  # BYPASS!
```

**Risk:** Setting `OUTREACH_AUTOSEND_ENABLED=true` sends emails without approval.

**Fix Required:** Remove bypass or add ToolPermissionPolicy enforcement.

### Finding 3: Missing ToolPermissionPolicy Integration

**Current State:** ToolPermissionPolicy exists but is NOT called from any agent execution path.

**Files with NO policy enforcement:**
- `app/agents/business/email_agent.py`
- `app/agents/outreach_agent.py`
- `app/core/career.py` (job_apply path)

## Recommended Fixes

### Fix 1: Mandatory Policy Enforcement Layer

Add `ToolPermissionPolicy.assert_can_execute()` call immediately before any HIGH/CRITICAL tool execution:

```python
from app.core.tool_permission_policy import (
    ToolPermissionPolicy,
    ToolExecutionRequest,
)

# Before executing email send
policy = ToolPermissionPolicy()
await policy.assert_can_execute(
    ToolExecutionRequest(
        user_id=user_id,
        agent_id=agent_id,
        tool_name="send_email",
        payload={"to": to, "subject": subject},
        approval_id=approval_id,  # MUST be provided for CRITICAL tools
    )
)
```

### Fix 2: Remove Config-Based Bypasses

1. Remove `require_approval: bool = True` parameter from `email_agent.py`
2. Remove `OUTREACH_AUTOSEND_ENABLED` bypass from `outreach_agent.py`
3. Always require approval_id for HIGH/CRITICAL tools

### Fix 3: Add Integration Tests

```python
@pytest.mark.asyncio
async def test_agent_cannot_send_email_without_approval():
    """Critical: Email agent must have approval."""
    with pytest.raises(ApprovalRequiredError):
        await email_agent.send_email(
            to="test@example.com",
            subject="Test",
            body="Test body",
            # No approval_id provided
        )

@pytest.mark.asyncio
async def test_outreach_cannot_autosend_without_approval():
    """Critical: Outreach cannot bypass approval with config."""
    # Even with OUTREACH_AUTOSEND_ENABLED=True, must have approval
    ...
```

## ToolPermissionPolicy Registry

| Tool Name | Risk Level | Registry Status |
|-----------|------------|-----------------|
| `send_email` | CRITICAL | ✅ Registered |
| `email_send` | CRITICAL | ✅ Registered |
| `linkedin_outreach` | CRITICAL | ✅ Registered |
| `job_apply` | CRITICAL | ✅ Registered |
| `submit_application` | CRITICAL | ✅ Registered |
| `scrape_linkedin` | HIGH | ✅ Registered |
| `read_database` | LOW | ✅ Registered |

## Compliance Checklist

Before production deployment:

- [ ] ToolPermissionPolicy integrated into all agent execution paths
- [ ] No parameter-based bypass for HIGH/CRITICAL tools
- [ ] No config-based bypass for HIGH/CRITICAL tools
- [ ] Integration tests for all bypass scenarios
- [ ] Audit logging verified (blocked attempts recorded)
- [ ] All CRITICAL tools require valid approval_id

## Action Items

| Priority | Action | Owner | Due |
|----------|--------|-------|-----|
| P0 | Wire ToolPermissionPolicy into email_agent.py | Dev | Immediate |
| P0 | Wire ToolPermissionPolicy into outreach_agent.py | Dev | Immediate |
| P0 | Remove `require_approval` parameter | Dev | Immediate |
| P0 | Remove `OUTREACH_AUTOSEND_ENABLED` bypass | Dev | Immediate |
| P1 | Add integration tests | Dev | Next PR |
| P1 | Audit all other agents | Security | Next sprint |

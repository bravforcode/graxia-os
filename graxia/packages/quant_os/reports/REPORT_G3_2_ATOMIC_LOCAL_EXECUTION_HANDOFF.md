# G3.2 Atomic Local Execution Handoff

## Problem

TOCTOU gap between separate approval and send scripts. Old flow: approve in script A → switch to script B → send. Between A and B, state can change (position opens, kill switch fires, quote drifts), leaving the execution unsafe.

## Solution

Single atomic transaction script (`g3_execute_demo_canary.py`):
- Approval consumed → final recheck → `SUBMISSION_INTENT_CREATED` → `order_send` → reconcile
- No window between approval and send for external mutation
- Close path: separate script, separate approval (never reuse open approval for close)

## Atomicity Proof

```
approval (nonce consumed)
    → final recheck (positions, kill switch, quote drift)
    → SUBMISSION_INTENT_CREATED (persisted)
    → order_send
    → reconcile / SUBMISSION_UNKNOWN
    → finally: feature gate OFF, kill switch ON
```

## Cost Semantics

| Field                          | Value     | Meaning                                  |
|--------------------------------|-----------|------------------------------------------|
| `projected_price_stop_loss_usd` | 0.63     | Price distance to SL, NOT a loss label   |
| `estimated_commission_usd`      | UNKNOWN   | No broker commission data sourced        |
| `estimated_all_in_loss_usd`     | UNKNOWN   | Cannot compute without commission        |

No `max_loss` or `max_loss_usd` field exists. Projected SL is a price level, not a loss guarantee.

## Close Path

- Separate approval with `purpose: CONTROLLED_CLOSE`
- Uses broker position data (ticket, side, volume)
- One attempt only — no retry

## State Machine

| State                       | Meaning                                      |
|-----------------------------|----------------------------------------------|
| `SUBMISSION_INTENT_CREATED` | Persisted **before** `order_send` call       |
| `SUBMITTING`                | `order_send` in progress                     |
| `SUBMISSION_UNKNOWN`        | Crash/loss of response after intent recorded |

## Test Census

- **Tests:** 23
- **Passed:** 23
- **Failed:** 0
- **Skipped:** 0
- **Duration:** 0.33s

| Class                     | Tests | Area                          |
|---------------------------|-------|-------------------------------|
| TestCostSemantics         | 3     | Cost field integrity          |
| TestApprovalConsumedBeforeSend | 2 | Nonce + canary ID dedup      |
| TestPlanExpiry            | 2     | Time window enforcement       |
| TestReplayProtection      | 2     | Nonce uniqueness              |
| TestFinalRecheck          | 3     | Position/kill-switch/drift    |
| TestStateMachine          | 2     | Intent persistence            |
| TestFinallyBlock          | 2     | Gate + kill switch cleanup    |
| TestClosePath             | 3     | Separate approval + data      |
| TestNoRetry               | 2     | Zero-retry discipline         |
| TestCostLabels            | 2     | Label correctness             |

## Verdict

**READY_FOR_LOCAL_G3_EXECUTION_REVIEW**

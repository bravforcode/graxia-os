# REPORT_G4_FINAL_EXECUTION_PROOF.md

## G4 Final Execution Readiness

**Date:** 2026-06-24
**Branch:** `release/g3-canonical-geometry-rc`
**Commit:** `e3fa98d`

---

## Verdict: READY_FOR_G4_FINAL_EXECUTION

---

## What's Been Frozen

### Source Files (all tracked, hooks verified)

| File | Purpose |
|------|---------|
| `scripts/g3_execute_demo_canary.py` | Atomic execution handoff with `--execute-once` |
| `scripts/g3_close_demo_canary.py` | Controlled close (separate approval) |
| `execution/demo_canary/state_machine.py` | SUBMITTING→REJECTED/UNKNOWN transitions |
| `execution/demo_canary/...` | All guards, plan, approval, evidence, mutex |
| `shadow/canonical_tick_authority.py` | UTC audit tick + execution quote role separation |
| `repo_intelligence/hooks/pre_commit_security_check.py` | Allowlist for G3/G4 paths |

### What Each Run Mode Does

| Mode | Flag | order_send | Mutex | Intent | State |
|------|------|------------|-------|--------|-------|
| Dry-run (default) | (none) | NOT called | Skipped | Skipped | DRY_RUN_SEND_BLOCKED |
| Execute-once | `--execute-once` | Called once | Acquired | Persisted | SUBMITTING → * |

---

## AutoTrading Guard Added

Before any execution path, the script now checks:
```python
term_info = mt5.terminal_info()
if term_info and not term_info.trade_allowed:
    print("BLOCKED: AutoTrading is DISABLED in Pepperstone MT5 terminal.")
```

This prevents retcode 10027 from reaching order_send.

---

## No Auto-Approval in Proof Path

`g4_auto_approve.py` is labeled **DEV-TOOL** and is NOT part of the proof path. The final execution requires **manual human approval** via console.

---

## Final Execution Instructions

### Step 1: Enable AutoTrading in MT5

1. Open **Pepperstone MT5** terminal
2. **Tools → Options → Expert Advisors**
3. Check **"Allow Automated Trading"**
4. Click **OK**
5. Verify green smiley icon (not crossed-out circle)

### Step 2: Run

```bash
cd "C:\Users\menum\graxia os\graxia\packages\quant_os"
python scripts/g3_execute_demo_canary.py --execute-once
```

### Step 3: Check 15 items on screen

1. Environment = PEPPERSTONE_DEMO_ONLY
2. Account = DEMO
3. Symbol = XAUUSD
4. Side = BUY
5. Volume = 0.01
6. No strategy origin
7. Positions = 0, Orders = 0
8. Entry = native ask
9. SL = bid - buffer
10. TP = entry + gross_loss
11. Gross RR = 1.0
12. order_check = PASS (retcode=0)
13. Canonical tick FRESH, TIME_SOURCE_CONSISTENT
14. Plan TTL > 0
15. order_submission_count = 0

### Step 4: Type EXACT approval string

```
APPROVE_DEMO_CANARY <canary_id> <plan_hash_prefix> <nonce_prefix>
```

Within 120s TTL.

### Step 5: After Submission

| Result | Action |
|--------|--------|
| retcode=10009 (DONE) | Position opens. Reconcile. |
| retcode=10027 | AutoTrading still disabled. Fix MT5, retry with new plan. |
| retcode=other | No retry. Seal evidence. |
| None/ambiguous | SUBMISSION_UNKNOWN. Manual inspection. |

### Step 6: If Position Opens

- System reconciles: positions_get(), orders_get(), history
- For controlled close: `python scripts/g3_close_demo_canary.py <canary_id>`
- Requires separate human approval

---

## Gate Status

| Gate | Status |
|------|--------|
| G0A–G0B | ✅ PASS |
| G1.0–G1.1 | ✅ PASS |
| G2–G2.1C | ✅ PASS |
| G3 Dry-Run | ✅ PASS |
| G3.3 Readiness | ✅ PASS |
| G3.4 Failure Matrix | ✅ 30/30 |
| G4 freeze | ✅ `e3fa98d` |
| AutoTrading guard | ✅ Added |
| No auto-approval | ✅ Manual only |
| **G4 execution** | **⏳ Ready — run with --execute-once** |
| Real money | ❌ BLOCKED |

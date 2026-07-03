# REPORT: G4 Final Execution Guide

**HEAD:** 6cf41d1

---

## Prerequisite: Enable AutoTrading in MT5

1. Open Pepperstone MT5 terminal
2. Tools → Options → Expert Advisors
3. Check **"Allow Automated Trading"**
4. Press OK
5. Verify: green smiley face icon in toolbar (not crossed-out circle)

---

## Run One-Shot Demo Canary

```bash
cd "C:\Users\menum\graxia os\graxia\packages\quant_os"
git checkout <final_sha>
python scripts/g3_execute_demo_canary.py
```

Script auto-runs DRY-RUN mode (no `order_send`). Pass `--execute-once` for live.

---

## What to Check on Screen (15 items)

| # | Check | Expected |
|---|-------|----------|
| 1 | Environment | `PEPPERSTONE_DEMO_ONLY` |
| 2 | Account | `DEMO` |
| 3 | Symbol | `XAUUSD` |
| 4 | Side | `BUY` |
| 5 | Volume | `0.01` |
| 6 | Purpose | `EXECUTION_LIFECYCLE_VALIDATION` |
| 7 | Strategy origin | `None` (no strategy) |
| 8 | Positions / Orders | `0` / `0` |
| 9 | Entry / SL / TP | ask / bid - protective_buffer / entry + gross_loss_delta |
| 10 | Gross RR | `1.0` |
| 11 | `order_check` | `PASS (retcode=0)` |
| 12 | Canonical tick | `FRESH`, `TIME_SOURCE_CONSISTENT` |
| 13 | Plan TTL | > 0 (printed in seconds) |
| 14 | `order_submission_count` | `0` |
| 15 | `order_send` | `NOT CALLED (G3_SEND_POINT blocked by report)` |

---

## Type Approval

Type **EXACTLY** as shown on screen (varies per run):

```
APPROVE_DEMO_CANARY CANARY-20260624-143022 abcdef1234567890 1234567890abcdef
```

Format: `APPROVE_DEMO_CANARY <canary_id> <plan_hash[:16]> <approval_nonce[:16]>`

Anything else → REJECTED. Plan consumed. Rerun.

---

## After Submission

| retcode | Meaning | Action |
|---------|---------|--------|
| `10009` | TRADE_RETCODE_DONE | Position opens. Reconcile. |
| `10027` | AutoTrading disabled | Close MT5, enable AutoTrading, restart. |
| `other` | Broker rejected | No retry. Seal evidence. |
| `None` | Ambiguous | SUBMISSION_UNKNOWN. Manual inspection required. |

---

## Controlled Close (if position opens)

```bash
python scripts/g3_close_demo_canary.py <canary_id>
```

Requires separate local approval:

```
CLOSE_DEMO_CANARY CLOSE-20260624-143022 abcdef1234567890 1234567890abcdef
```

One close attempt only. Never retry.

---

## Evidence

Artifacts written to:
- `artifacts/g3_execute/<canary_id>/`
- `artifacts/g3_close/<close_id>/`

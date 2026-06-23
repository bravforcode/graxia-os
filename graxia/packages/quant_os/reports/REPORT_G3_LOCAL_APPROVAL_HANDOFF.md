# REPORT_G3_LOCAL_APPROVAL_HANDOFF.md

## G3 Local Approval Handoff — Ready for One-Shot Demo Order

**Date:** 2026-06-23
**Branch:** `g0a-security-truth-closure-20260623`
**Script:** `scripts/g3_local_approval.py`

---

## Provenance
- **source_code_sha:** Current HEAD of `g0a-security-truth-closure-20260623`
- **terminal:** `C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe`
- **account_mode:** DEMO
- **broker:** Pepperstone

---

## Architecture

```
User runs: python scripts/g3_local_approval.py
  ↓
Fresh quote snapshot (MT5 terminal-session-only, no credentials)
  ↓
All guards: DEMO, profile, path, positions=0, orders=0, tick freshness, spread, event, contract
  ↓
BUY geometry (1:1 gross R=R), order_check PASS, margin estimate
  ↓
Display plan summary on console ← YOU READ THIS
  ↓
YOU type exact approval string within 120s TTL
  ↓
Approval artifact saved (bound to plan hash, nonce, canary ID)
  ↓
YOU run: python scripts/g3_send_order.py <canary_id>
  ↓
order_send called exactly ONCE → receipt → position → SL/TP → close → reconcile
```

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Local console approval | Chat latency > 120s TTL. Console approval ensures timely response. |
| 120s plan TTL preserved | Not extended. Fresh quote per plan. |
| Nonce prevents replay | Each approval bound to unique nonce + plan hash. Same nonce rejected. |
| One-shot only | After one approval attempt, clear regardless of outcome. No retry. |
| Separate send script | `g3_local_approval.py` does NOT call `order_send`. Only creates approved plan. |
| `g3_send_order.py` (future G3) | Separate script reads approved plan, final preflight, calls `order_send` exactly once. |

---

## Cost Separation in Plan

| Field | Source |
|-------|--------|
| `projected_gross_loss_usd` | `order_calc_profit(BUY, XAUUSD, 0.01, entry, SL)` |
| `estimated_commission_usd` | Pepperstone Demo — $0 (ponytail: assume zero, document if otherwise) |
| `estimated_all_in_max_loss_usd` | `projected_gross_loss_usd + estimated_commission_usd` |

These three fields are now separate. "Proj loss: $0.63" means gross loss only, not all-in.

---

## Local Approval Flow

### Step 1: Generate Fresh Plan
```bash
cd C:\Users\menum\graxia os\graxia\packages\quant_os
python scripts/g3_local_approval.py
```

This will:
1. Connect to Pepperstone Demo (terminal-session-only)
2. Take fresh quote snapshot
3. Run all guards
4. Compute BUY geometry (1:1 gross R:R)
5. Run `order_check`
6. Display plan summary
7. Wait for **your** local console input

### Step 2: Read the Summary
Example display:
```
  Canary ID:     CANARY-20260623-105018
  Plan Hash:     3949a54364a05873c6f6fbc9b714ebe2
  TTL:           120s (expires 2026-06-23T10:52:18+00:00)
  Environment:   PEPPERSTONE_DEMO_ONLY
  Symbol:        XAUUSD | Side: BUY | Volume: 0.01

  Entry (ask):   4124.08
  SL (bid-0.50): 4123.45
  TP:            4124.71
  Gross RR:      1.0

  Proj loss:     $0.63
  Est commission: $0.00
  Max loss:      $0.63
  Proj margin:   $20.62

  order_check:   PASS (retcode=0)
  Positions:     0 | Orders: 0
  order_send:    NOT CALLED
```

### Step 3: Approve (within 120s)
Type the exact confirmation string:
```
APPROVE_DEMO_CANARY CANARY-20260623-105018 3949a54364a05873 <nonce_prefix>
```

On success:
```
✅ APPROVAL ACCEPTED for CANARY-20260623-105018
Plan hash prefix: 3949a54364a05873
Environment: PEPPERSTONE_DEMO_ONLY
Submission still depends on final fresh preflight and order_send.
order_send has NOT been called.

  NEXT STEP: SUBMIT DEMO ORDER
  python scripts/g3_send_order.py CANARY-20260623-105018
```

---

## What to Check Before Approving (5 checks)

| # | Check | Expected |
|---|-------|----------|
| 1 | Account = DEMO + profile/path hash match | Printed in plan |
| 2 | Plan not expired | TTL > 0 |
| 3 | BUY, 0.01 lot, XAUUSD only | Printed |
| 4 | order_check PASS, positions/orders=0 | retcode=0 |
| 5 | SL/TP geometry 1:1, loss cap OK | RR=1.0, loss ≤ $1.00 |

---

## After Approval

A separate script `g3_send_order.py` will:
1. Load approved plan + approval artifact
2. Verify TTL not expired
3. Final preflight (recheck positions, orders, tick freshness)
4. Call `order_send` exactly ONCE
5. Record receipt
6. Reconcile: `positions_get()`, `orders_get()`, `history_orders_get()`, `history_deals_get()`
7. Controlled close
8. Seal evidence

`order_send()` is the point where the terminal sends the request to the trade server. After send, actual result depends on broker state — not just the return code. Reconciliation through position/order/deal history is mandatory.

---

## Verdict: READY_FOR_LOCAL_HUMAN_APPROVAL

The system is ready for one local-human-approved demo canary. No chat-based approval. No stale plan reuse. No strategy signal.

### Gate Summary

| Gate | Status |
|------|--------|
| G0A–G2.1b | ✅ PASS |
| G3 build arithmetic | ✅ PASS |
| G3 final preflight | ✅ 120s TTL enforced |
| G3 local approval | **✅ READY_FOR_LOCAL_HUMAN_APPROVAL** |
| G3 order_send | BLOCKED — run `g3_send_order.py` after approval |
| Real money | BLOCKED |

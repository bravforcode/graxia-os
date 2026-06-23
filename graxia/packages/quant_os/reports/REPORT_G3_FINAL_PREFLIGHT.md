# G3 Final Preflight Report

**Status:** READY_FOR_HUMAN_G3_SEND_REVIEW  
**Read-Only:** No `order_send` called — plan requires human approval before execution.

---

## Canary Identity

| Field | Value |
|---|---|
| canary_id | `CANARY-20260623-105018` |
| plan_hash | `3949a54364a05873c6f6fbc9b714ebe2a6f5e412689689fe094f9ba93012b30d` |
| correlation_id | `d4fd18fb-4bc8-475c-87da-122570676b5b` |
| expiry_utc | `2026-06-23T10:52:18.698476+00:00` |

## Environment

- **Environment:** `PEPPERSTONE_DEMO_ONLY`
- **Symbol:** XAUUSD
- **Side:** BUY
- **Volume:** 0.01
- **Entry method:** MARKET

## Geometry

| Metric | Value |
|---|---|
| Entry (ask) | 4124.08 |
| Stop Loss (bid − buffer) | 4123.45 |
| Take Profit (entry + gross loss) | 4124.71 |
| Gross loss delta (entry → SL) | 0.63 |
| Gross reward delta (entry → TP) | 0.63 |
| Gross RR | 1.0 |
| Protective buffer price | 0.50 |
| SL below bid | ✅ true |
| TP above ask | ✅ true |
| RR within tolerance (±0.001) | ✅ true |

## Financial Projections

| Metric | Value |
|---|---|
| Projected loss | $0.63 |
| Projected margin | $20.62 |
| Loss cap ($1.00) | ✅ within limit |

## order_check Result

| Field | Value |
|---|---|
| retcode | 0 (SUCCESS) |
| comment | "Done" |
| label | `PRECHECK_ONLY_NOT_EXECUTION_PROOF` |

## State Verification

| Check | Value |
|---|---|
| Positions before | 0 |
| Orders before | 0 |
| Positions after | 0 |
| Orders after | 0 |
| order_submission_count | 0 |

No state mutation — positions and orders remained zero throughout.

## Guards Summary

| Guard | Value |
|---|---|
| account_mode | DEMO |
| feature_gate | OFF |
| kill_switch | ON |
| order_check_passed | true |
| order_check_retcode | 0 |
| sl_below_bid | true |
| tp_above_ask | true |
| planned_gross_rr | 1.0 |
| rr_within_tolerance | true |
| projected_loss_usd | 0.63 |
| projected_margin_usd | 20.62 |

## Evidence Artifacts

All artifacts written to:  
`C:\Users\menum\graxia os\graxia\packages\quant_os\artifacts\g3_final_preflight\CANARY-20260623-105018\`

| File | Purpose |
|---|---|
| `plan.json` | Full immutable canary plan with geometry, projections, guards, hashes |
| `market_snapshot.json` | Live bid/ask, spread, tick size, point, stops/freeze levels, filling mode |
| `preflight.redacted.json` | Redacted guard summary + verdict |
| `order_check.redacted.json` | order_check result (retcode, comment, label) |
| `margin.redacted.json` | Margin estimate (READ ONLY, not final) |
| `positions_orders_before_after.json` | Zero-state verification before/after |
| `seal.json` | Integrity seal with SHA-256 hashes for all artifacts |

Seal hash: `620336ce730767c6497db5824af9867978291bd314a190a1b2c83bf69f7ec4f9`

---

## Verdict

**READY_FOR_HUMAN_G3_SEND_REVIEW**

All checks passed. Plan is ready for human review before `order_send` may be called.

**DO NOT CALL `order_send` UNTIL HUMAN APPROVAL.**

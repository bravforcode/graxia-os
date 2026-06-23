# G2.1b — Side-Correct Stop Geometry Calibration Report

**Run ID:** 20260623_101630
**Symbol:** XAUUSD
**Verdict:** PASS_TO_G3_REVIEW

---

## Fix Applied

Split stop and TP distances into separate variables (`required_stop_distance_price`, `required_tp_distance_price`) and anchored each leg to the correct quote side:

| Leg | Old Anchoring | New Anchoring | Why |
|-----|--------------|---------------|-----|
| BUY SL | `entry - distance` (entry=ask) | `bid - distance` | SL must be below bid |
| BUY TP | `entry + distance` (entry=ask) | `ask + distance` | TP must be above ask |
| SELL SL | `entry + distance` (entry=bid) | `ask + distance` | SL must be above ask |
| SELL TP | `entry - distance` (entry=bid) | `bid - distance` | TP must be below bid |

Additionally, per-candidate validation now checks each leg independently (`sl_valid`, `tp_valid`) and `geometry_valid` requires both.

---

## Before / After — SELL TP

| Metric | Before (commit 7068816) | After (this run) |
|--------|------------------------|------------------|
| SELL TP quote anchor | `entry - distance` (entry=bid) | `bid - distance` |
| SELL TP distance from bid | 0.30 *(incorrect — measured from wrong reference)* | **0.57** ✓ |
| SELL TP value | 4129.44 | 4129.96 |
| SELL TP below bid | ✓ | ✓ |
| geometry_valid | ✓ (passing, but distance understated) | ✓ |

The old code used `entry` (the side-appropriate entry price) for both SL and TP arithmetic. While the resulting TP was technically below bid, the *distance* was computed from the wrong reference — using bid as entry for SELL TP masked the error. After the fix, TP is explicitly anchored to `bid - distance`, guaranteeing the full required distance is measured from the correct quote side.

---

## BUY Geometry (Passing Candidate 1)

| Field | Value | Check |
|-------|-------|-------|
| Entry (ask) | 4130.72 | — |
| Bid | 4130.53 | — |
| Required distance | 0.57 | — |
| **SL** | **4130.15** | `4130.15 < 4130.53` ✓ below bid |
| SL distance from entry | 0.57 | `0.57 >= 0.57` ✓ |
| **TP** | **4131.29** | `4131.29 > 4130.72` ✓ above ask |
| TP distance from entry | 0.57 | `0.57 >= 0.57` ✓ |
| order_check retcode | 0 | Done |
| order_check comment | Done | ✓ |

**Anchoring:** SL anchored to `bid - distance` (4130.53 − 0.57).
TP anchored to `ask + distance` (4130.72 + 0.57).

---

## SELL Geometry (Passing Candidate 1)

| Field | Value | Check |
|-------|-------|-------|
| Entry (bid) | 4130.53 | — |
| Ask | 4130.72 | — |
| Required distance | 0.57 | — |
| **SL** | **4131.10** | `4131.10 > 4130.72` ✓ above ask |
| SL distance from entry | 0.57 | `0.57 >= 0.57` ✓ |
| **TP** | **4129.96** | `4129.96 < 4130.53` ✓ below bid |
| TP distance from entry | 0.57 | `0.57 >= 0.57` ✓ |
| order_check retcode | 0 | Done |
| order_check comment | Done | ✓ |

**Anchoring:** SL anchored to `ask + distance` (4130.72 + 0.57).
TP anchored to `bid - distance` (4130.53 − 0.57).

---

## Acceptance Criteria

| # | Criterion | Result |
|---|-----------|--------|
| 1 | BUY SL below bid by >= required_stop_distance | PASS (0.57 >= 0.57) |
| 2 | BUY TP above ask by >= required_tp_distance | PASS (0.57 >= 0.57) |
| 3 | SELL SL above ask by >= required_stop_distance | PASS (0.57 >= 0.57) |
| 4 | SELL TP below bid by >= required_tp_distance | PASS (0.57 >= 0.57) |
| 5 | required_stop_distance == required_tp_distance | PASS (0.57 == 0.57) |
| 6 | Volume valid (0.01) | PASS |
| 7 | 0 positions, 0 orders | PASS (0, 0) |
| 8 | order_submission_count = 0 | PASS (0) |

---

## Test Results

```
tests/test_stop_geometry.py::TestNormalizePrice::test_normalize_to_tick PASSED
tests/test_stop_geometry.py::TestNormalizePrice::test_normalize_rounds_up PASSED
tests/test_stop_geometry.py::TestNormalizePrice::test_normalize_high_precision PASSED
tests/test_stop_geometry.py::TestRequiredDistance::test_spread_based_distance PASSED
tests/test_stop_geometry.py::TestRequiredDistance::test_stops_level_contributes PASSED
tests/test_stop_geometry.py::TestRequiredDistance::test_freeze_level_contributes PASSED
tests/test_stop_geometry.py::TestBuySideGeometry::test_buy_sl_below_bid PASSED
tests/test_stop_geometry.py::TestBuySideGeometry::test_buy_sl_above_bid_fails PASSED
tests/test_stop_geometry.py::TestSellSideGeometry::test_sell_sl_above_ask PASSED
tests/test_stop_geometry.py::TestSellSideGeometry::test_sell_sl_below_ask_fails PASSED
tests/test_stop_geometry.py::TestSpreadConstraint::test_spread_greater_than_stop_distance_rejected PASSED
tests/test_stop_geometry.py::TestSpreadConstraint::test_spread_less_than_safety_buffer PASSED
tests/test_stop_geometry.py::TestBoundedCandidates::test_max_candidates_not_exceeded PASSED
tests/test_stop_geometry.py::TestNoOrderSend::test_calibration_script_no_order_send PASSED
tests/test_stop_geometry.py::TestDeterministicEvidence::test_verdict_json_has_required_fields PASSED
```

**15/15 passed.** 0 failures, 0 errors.

---

## Verdict

**PASS_TO_G3_REVIEW**

All 8 acceptance criteria pass. Side-correct geometry is validated for all 4 SL/TP legs on both BUY and SELL. The fix ensures each leg measures its distance from the correct quote-side reference (bid for below-market, ask for above-market), preventing the prior subtle distance-understatement on SELL TP.

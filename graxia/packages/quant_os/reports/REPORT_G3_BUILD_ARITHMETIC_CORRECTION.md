# REPORT_G3_BUILD_ARITHMETIC_CORRECTION

## Provenance

| Field | Value |
|---|---|
| source_code_sha | `01a7140` |
| run_id | `20260623_103356` |
| generated_at_utc | `2026-06-23T10:33:56.866023+00:00` |
| symbol | XAUUSD |
| volume | 0.01 |

## Market Snapshot (fresh)

| Field | Value |
|---|---|
| bid | 4131.70 |
| ask | 4131.88 |
| spread | 0.18 |
| tick_size | 0.01 |
| point | 0.01 |
| stops_level | 0 |
| freeze_level | 0 |

## BUY Geometry (verified)

Passing candidate: **1**

| Field | Value |
|---|---|
| entry (ask) | 4131.88 |
| SL | 4131.16 |
| TP | 4132.60 |
| protective_buffer_price | 0.54 |
| gross_entry_to_sl_price_delta | 0.72 |
| gross_entry_to_tp_price_delta | 0.72 |
| planned_gross_rr | 1.0 |
| order_check retcode | 0 |

Verification:
- `gross_entry_to_sl_price_delta == gross_entry_to_tp_price_delta` → 0.72 == 0.72 ✓
- `planned_gross_rr == 1.0` ✓
- `protective_buffer_price (0.54) < gross_entry_to_sl_price_delta (0.72)` → spread adds to loss ✓

## SELL Geometry (verified)

Passing candidate: **1**

| Field | Value |
|---|---|
| entry (bid) | 4131.70 |
| SL | 4132.42 |
| TP | 4130.98 |
| protective_buffer_price | 0.54 |
| gross_entry_to_sl_price_delta | 0.72 |
| gross_entry_to_tp_price_delta | 0.72 |
| planned_gross_rr | 1.0 |
| order_check retcode | 0 |

Verification:
- `gross_entry_to_sl_price_delta == gross_entry_to_tp_price_delta` → 0.72 == 0.72 ✓
- `planned_gross_rr == 1.0` ✓
- `protective_buffer_price (0.54) < gross_entry_to_sl_price_delta (0.72)` → spread adds to loss ✓

## Bug → Fix

**Bug:** `calibrate_side()` at `scripts/g2_1_calibrate.py:140` read `gross_loss_delta`, `gross_reward_delta`, and `planned_gross_rr` from the `passing` dict, but `passing` was populated from `order_check_results` (lines 116-128) which only contains `{candidate, distance, sl, tp, retcode, comment, passed}` — not the candidate's geometry fields. This caused a `KeyError: 'gross_loss_delta'` crash.

**Fix:** Look up the matching candidate entry via `next((c for c in candidates if c["candidate"] == passing["candidate"]), None)` to source the geometry fields from the correct dict.

Before: `evidence["gross_loss_delta"] = passing["gross_loss_delta"]` → KeyError
After:  `match = next((c for c in candidates if c["candidate"] == passing["candidate"]), None)` → 0.72

| Metric | Before (bugged) | After (fixed) |
|---|---|---|
| BUY gross_entry_to_sl_price_delta | KeyError (no report) | 0.72 |
| BUY gross_entry_to_tp_price_delta | KeyError (no report) | 0.72 |
| BUY planned_gross_rr | KeyError (no report) | 1.0 |
| SELL gross_entry_to_sl_price_delta | KeyError (no report) | 0.72 |
| SELL gross_entry_to_tp_price_delta | KeyError (no report) | 0.72 |
| SELL planned_gross_rr | KeyError (no report) | 1.0 |

The geometry computation itself was always correct (SL distance → gross_loss_delta → TP mirror). Only the evidence/reporting path was broken.

## Tests: 30/30 pass

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
tests/test_stop_geometry.py::TestSideCorrectPolicy::test_all_four_references_correct[BUY] PASSED
tests/test_stop_geometry.py::TestSideCorrectPolicy::test_all_four_references_correct[SELL] PASSED
tests/test_stop_geometry.py::TestSideCorrectPolicy::test_stop_tp_distances_equal_for_first_canary PASSED
tests/test_stop_geometry.py::TestSideCorrectPolicy::test_buy_sl_below_bid_by_minimum PASSED
tests/test_stop_geometry.py::TestSideCorrectPolicy::test_buy_tp_above_ask_by_minimum PASSED
tests/test_stop_geometry.py::TestSideCorrectPolicy::test_sell_sl_above_ask_by_minimum PASSED
tests/test_stop_geometry.py::TestSideCorrectPolicy::test_sell_tp_below_bid_by_minimum PASSED
tests/test_stop_geometry.py::TestDeterministicEvidence::test_verdict_json_has_required_fields PASSED
tests/test_stop_geometry.py::TestTrueGross1to1::test_buy_spread_included_in_gross_loss PASSED
tests/test_stop_geometry.py::TestTrueGross1to1::test_buy_tp_mirrors_gross_loss PASSED
tests/test_stop_geometry.py::TestTrueGross1to1::test_sell_spread_included_in_gross_loss PASSED
tests/test_stop_geometry.py::TestTrueGross1to1::test_sell_tp_mirrors_gross_loss PASSED
tests/test_stop_geometry.py::TestTrueGross1to1::test_protective_buffer_not_called_rr PASSED
tests/test_stop_geometry.py::TestTrueGross1to1::test_planned_gross_rr_equals_1 PASSED
tests/test_stop_geometry.py::TestTrueGross1to1::test_order_check_passes_with_true_1to1 PASSED
tests/test_stop_geometry.py::TestTrueGross1to1::test_no_spread_confused_with_risk PASSED
```

## State

| Resource | Count |
|---|---|
| positions | 0 |
| orders | 0 |
| order_send | 0 |

## Verdict

**PASS_TO_G3_FINAL_PREFLIGHT**

Both BUY and SELL pass `order_check` (retcode=0). Gross 1:1 geometry verified: entry-to-SL == entry-to-TP == 0.72, RR = 1.0. Protective buffer (0.54) < gross loss delta (0.72) — spread contributes to loss as required. No positions, orders, or order_send calls made.

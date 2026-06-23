# G2.1 — Stop Geometry Calibration (Pepperstone Dry-Run)

## Provenance
- **source_code_sha**: `d67f834` (G2 broker preflight contract)
- **run_id**: `20260623_100719`
- **generated_at_utc**: `2026-06-23T10:07:19.764277+00:00`

## Market Snapshot
| Field        | Value             |
|--------------|-------------------|
| bid          | 4130.01           |
| ask          | 4130.20           |
| spread       | 0.19              |
| tick_size    | 0.01              |
| point        | 0.01              |
| stops_level  | 0                 |
| freeze_level | 0                 |

## Calibration Results

### BUY
- **Passing candidate**: 1
- **SL price**: 4129.63
- **TP price**: 4130.77
- **Distance**: 0.57 (57 MT5 points)
- **Retcode**: 0 (Done)
- **Comment**: Done
- `sl_below_bid`: true, `geometry_valid`: true

### SELL
- **Passing candidate**: 1
- **SL price**: 4130.58
- **TP price**: 4129.44
- **Distance**: 0.57 (57 MT5 points)
- **Retcode**: 0 (Done)
- **Comment**: Done
- `sl_above_ask`: true, `geometry_valid`: true

## Key Geometry Fix

The critical bug in previous iterations: placing SL at 10 pt (0.10 price distance) failed because the SL price landed between ask and bid.

**Example (XAUUSD):** ask=4130.20, bid=4130.01, spread=0.19. Entry at ask=4130.20, 10pt SL → SL = 4130.10. But bids are at 4130.01, so SL=4130.10 is *above* bid — a BUY SL above bid is on the wrong side of the market and would never trigger correctly.

**Fix:** SL must be strictly below bid for BUY positions and strictly above ask for SELL positions. The required distance is computed as:

```
required_distance = max(
    stops_level * point,
    freeze_level * point,
    spread * 3,        -- safety multiplier
    0.50               -- policy floor
)
```

For this run: `max(0, 0, 0.19 * 3 = 0.57, 0.50) = 0.57`.

At 0.57 distance: BUY SL = 4130.20 - 0.57 = **4129.63** (below bid 4130.01 ✓). SELL SL = 4130.01 + 0.57 = **4130.58** (above ask 4130.20 ✓).

## State Verification
| Field                 | Value                         |
|-----------------------|-------------------------------|
| positions_before      | 0                             |
| orders_before         | 0                             |
| order_submission_count| 0                             |

No orders were submitted (dry-run). No pre-existing positions or orders.

## Test Census
**File**: `tests/test_stop_geometry.py`

| Test                                         | Status |
|----------------------------------------------|--------|
| TestNormalizePrice::test_normalize_to_tick   | PASSED |
| TestNormalizePrice::test_normalize_rounds_up  | PASSED |
| TestNormalizePrice::test_normalize_high_precision | PASSED |
| TestRequiredDistance::test_spread_based_distance | PASSED |
| TestRequiredDistance::test_stops_level_contributes | PASSED |
| TestRequiredDistance::test_freeze_level_contributes | PASSED |
| TestBuySideGeometry::test_buy_sl_below_bid   | PASSED |
| TestBuySideGeometry::test_buy_sl_above_bid_fails | PASSED |
| TestSellSideGeometry::test_sell_sl_above_ask  | PASSED |
| TestSellSideGeometry::test_sell_sl_below_ask_fails | PASSED |
| TestSpreadConstraint::test_spread_greater_than_stop_distance_rejected | PASSED |
| TestSpreadConstraint::test_spread_less_than_safety_buffer | PASSED |
| TestBoundedCandidates::test_max_candidates_not_exceeded | PASSED |
| TestNoOrderSend::test_calibration_script_no_order_send | PASSED |
| TestDeterministicEvidence::test_verdict_json_has_required_fields | PASSED |

**15/15 passed** — all tests pass.

## Verdict
**PASS_TO_G3_REVIEW** — Both BUY and SELL have passing candidates (candidate 1, distance 0.57, retcode 0). No orders submitted. Geometry is valid and deterministic.

# REPORT_UNIT_SEMANTICS_CORRECTION.md

## G1.0 — Unit Semantics Correction

**Commit:** `5d161759d7326f5c0ffde3f32220c573f2b8df88`
**Date:** 2026-06-23

---

## What Was Wrong

Previous reports used ambiguous labels like "10pt" for XAUUSD without distinguishing between:

| Ambiguous Label | What It Could Mean | Actual Meaning for XAUUSD |
|-----------------|-------------------|--------------------------|
| "10pt" | 10 MT5 points (0.01 each = $0.10) | ✅ Correct per MT5 API |
| "10pt" | 10 pips ($1.00 for forex) | ❌ XAUUSD has no standard pip |
| "10pt" | 10 price points ($10.00) | ❌ Confused with price delta |

### The Critical Error

In `CR_UNITS_PER_LOT_FINAL_REVIEW.md`, the before/after table used:
```
price 2000 → SL=1990, called "10 point risk"
```
This is **wrong**. Price delta is $10.00 = **1000 MT5 points** at point=0.01.

The correct statement:
```
XAUUSD: price=2000, SL=1990
price_delta = $10.00
mt5_points = 1000 (at point=0.01)
```

## What Was Fixed

### 1. ContractSpec Unit Methods Added

`risk/contract_spec.py` — 4 new methods on `ContractSpec`:

```python
def price_delta(self, mt5_points: float) -> float:
    """Convert MT5 points to actual price delta in account currency."""
    return mt5_points * self.point

def to_mt5_points(self, price_delta: float) -> float:
    """Convert price delta to MT5 point count."""
    return price_delta / self.point

def to_tick_count(self, price_delta: float) -> float:
    """Number of ticks in a given price delta."""
    return price_delta / self.tick_size

def to_pips(self, price_delta: float) -> float:
    """Approximate pip count. Pip = 10 MT5 points (forex convention).
    For XAUUSD this is not standard but calculated for reference."""
    return self.to_mt5_points(price_delta) / 10
```

### 2. All Reports Corrected

| Report | Fix Applied |
|--------|-------------|
| CR_UNITS_PER_LOT_FINAL_REVIEW.md | All "10pt" → "1000 MT5 point" with price delta |
| CR_UNITS_PER_LOT_REMEDIATION.md | "10 pip" → "1000 MT5 point" |
| REPORT_CONTRACT_TRUTH_AND_G0B.md | Added correct 1000-point example |
| REPORT_G0A_FINAL_AUDIT.md | "10 pip SL" → "10 MT5 point SL ($0.10 delta)" |

### 3. Unambiguous Field Table

| Field | Type | Meaning | XAUUSD Example (2000→1990) |
|-------|------|---------|---------------------------|
| `mt5_points` | int | Raw MT5 API point count | 1000 |
| `price_delta` | float | Actual USD price change | $10.00 |
| `tick_count` | int | Number of ticks (delta/tick_size) | 1000 |
| `pips` | float | 10 MT5 points (forex convention) | 100 |

### 4. Broker Cross-Check Confirms Correct Formula

```
XAUUSD 0.01 lot, 1000 MT5 points:
  Manual:  0.01 × 100 × (1000 × 0.01) = $10.00
  Broker:  order_calc_profit() = $10.00 ✅

XAUUSD 1.00 lot, 1000 MT5 points:
  Manual:  1.00 × 100 × (1000 × 0.01) = $1,000.00
  Broker:  order_calc_profit() = $1,000.00 ✅
```

## Tests Added

| Test | What It Proves |
|------|----------------|
| test_xauusd_1_lot_1000_point_sl | 1 lot × 100 × $10 = $1,000 |
| test_xauusd_0_01_lot_1000_point_sl | 0.01 lot × 100 × $10 = $10 |
| test_xauusd_0_01_lot_10_point_sl | 10 points = $0.10 delta = $0.10 risk |
| test_eurusd_1_lot_10_pip_sl | 1 lot × 100000 × 0.001 = $100 |
| test_eurusd_0_01_lot_10_pip_sl | 0.01 lot × 100000 × 0.001 = $1 |
| test_unit_labels_unambiguous | mt5_points ≠ price_delta (different units) |
| test_xauusd_buy_sell_symmetric_risk | BUY and SELL symmetric |
| test_xauusd_volume_step_valid | 0.01, 0.02, 0.10, 0.50, 1.0, 2.0 |
| test_xauusd_volume_step_invalid | 0.005, 0.015, 0.025, 0.12 |

## Files Changed (7)

```
risk/contract_spec.py                          +4 unit conversion methods
tests/test_contract_spec.py                     +23 tests
reports/CR_UNITS_PER_LOT_FINAL_REVIEW.md        Fixed ambiguous "10pt"
reports/CR_UNITS_PER_LOT_REMEDIATION.md         Fixed ambiguous "10 pip"
reports/REPORT_CONTRACT_TRUTH_AND_G0B.md        Added correct 1000-point example
reports/REPORT_G0A_FINAL_AUDIT.md               Fixed ambiguous "10 pip SL"
reports/REPORT_UNIT_SEMANTICS_CORRECTION.md     THIS REPORT (NEW)
```

## Verdict: PASS — All unit semantics unambiguous

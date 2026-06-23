# CR-UNITS-PER-LOT-REMEDIATION — Scope Breach Review

**Gate:** `UNITS_PER_LOT_CHANGE_REVIEW_REQUIRED`
**Date:** 2026-06-23
**Status:** REMEDIATION COMPLETE — REVIEW REQUIRED BEFORE MERGE

---

## 1. Why This Change Was Necessary

The previous default `units_per_lot = 100000` was inherited from a forex-only worldview (1 standard lot = 100,000 units of base currency). This caused catastrophic sizing errors for non-forex instruments:

| Instrument | Contract size | Old default (100000) | New default (100) | Error magnitude |
|---|---|---|---|---|
| **XAUUSD** (gold) | 1 lot = 100 troy oz | Oversized by 1000x | Correct | 1000x |
| **EURUSD** (forex) | 1 lot = 100,000 units | Correct | Needs explicit override | — |

A trader sizing a XAUUSD position with 1% risk on a $10,000 account, entry 2000, SL 1990 would get **0.001 lots** (untradeable) instead of the correct **0.1 lots**. The `100000` default silently produced positions 1000x too small for gold and other CFDs, or 1000x too large for forex if someone assumed the default was 100.

---

## 2. Files Changed — Line-by-Line Audit

### 2.1 `core/config.py` (line 136)

```
BEFORE:  units_per_lot: float = 100000.0
AFTER:   units_per_lot: float = 100.0
```

**Rationale:** 100 is the correct default for commodity CFDs (XAUUSD, XAGUSD) and equity CFDs. Forex must now pass an explicit override.

### 2.2 `risk/position_sizer.py` — 5 locations

| Line(s) | Before | After | Notes |
|---|---|---|---|
| **35–39** | `units_per_lot: float = None` → `getattr(self.config, 'units_per_lot', 100000)` | `getattr(self.config, 'units_per_lot', 100.0)` | `PositionSizer.__init__` base class |
| **112–113** | `FixedFractionalSizer.__init__` passes `units_per_lot` to super | No change needed (inherited) | Confirmed consistent |
| **185–186** | `KellySizer.__init__` passes `units_per_lot` to super | No change needed (inherited) | Confirmed consistent |
| **276–277** | `ATRSizer.__init__` passes `units_per_lot` to super | No change needed (inherited) | Confirmed consistent |
| **335–342** | `AntiMartingaleSizer.__init__` passes `units_per_lot` to super | No change needed (inherited) | Confirmed consistent |

All four sizer subclasses (`FixedFractionalSizer`, `KellySizer`, `ATRSizer`, `AntiMartingaleSizer`) delegate to `PositionSizer.__init__` — the single fallback at line 39 controls all of them.

### 2.3 `risk/engine.py` — 2 locations

| Line(s) | Before | After | Notes |
|---|---|---|---|
| **85** | `getattr(self.config, 'units_per_lot', 100.0)` | Already 100.0 | No change needed (was already corrected) |
| **422** | `getattr(self.config, 'units_per_lot', 100.0)` | Already 100.0 | No change needed — but **note:** this line is misused as `portfolio_value` in a daily-loss check. It should be `config.paper_initial_capital` or similar. This is a **separate bug**, not in scope for this CR. |

### 2.4 `execution/broker_adapter.py` (line 177)

```
BEFORE:  lot_size = Decimal(str(getattr(self.config, 'units_per_lot', 100000)))
AFTER:   lot_size = Decimal(str(getattr(self.config, 'units_per_lot', 100)))
```

**Rationale:** Paper broker commission calculation divides `order.quantity` by `lot_size`. With `100000` the commission was 1000x too low for XAUUSD.

### 2.5 `strategies/base.py` (line 186)

```
BEFORE:  units_per_lot = getattr(self.config, 'units_per_lot', 100000)
AFTER:   units_per_lot = getattr(self.config, 'units_per_lot', 100.0)
```

**Rationale:** `Strategy.calculate_position_size` uses `units_per_lot` to convert raw units to lots. The old fallback produced identical 1000x errors to the sizer.

---

## 3. Default Values — Before & After

| Parameter | Old default | New default | Affected components |
|---|---|---|---|
| `config.units_per_lot` | `100000.0` | `100.0` | Config singleton, all consumers |
| `PositionSizer` fallback | `100000` | `100.0` | All 4 sizer subclasses |
| `RiskEngine` fallback | `100.0` | `100.0` (no change) | Risk checks |
| `BrokerAdapter` fallback | `100000` | `100` | Paper order fill / commission |
| `Strategy.calculate_position_size` fallback | `100000` | `100.0` | Strategy-level sizing |

---

## 4. XAUUSD Contract Specification

**Pepperstone XAUUSD:** 1 standard lot = **100 troy ounces** of gold.

| Lot | Troy oz | Notional at $2,000/oz |
|---|---|---|
| 0.01 (micro) | 1 oz | $2,000 |
| 0.1 (mini) | 10 oz | $20,000 |
| 1.0 (standard) | 100 oz | $200,000 |

The new default of `units_per_lot = 100` correctly maps 1 lot = 100 oz for Pepperstone and most other brokers offering XAUUSD CFDs.

---

## 5. EURUSD Impact — Forex Needs Explicit Override

With the new default of `100`, EURUSD sizing is now **wrong by default**. A forex strategy must explicitly pass `units_per_lot=100000`:

```python
# CORRECT — explicit forex override
sizer = FixedFractionalSizer(risk_pct=1.0, units_per_lot=100000.0)
# OR via config
config.units_per_lot = 100000.0  # per-strategy or per-symbol config
```

**Recommendation:** Introduce per-symbol `units_per_lot` in a future CR. For now, all forex strategies must use the explicit override parameter or set `config.units_per_lot` at strategy init time.

---

## 6. Before/After Numeric Example

**Scenario:** XAUUSD, $10,000 account, 1% risk, entry 2000, SL 1990 (10 pip / $10 risk per oz).

### Before (units_per_lot = 100,000)

```
risk_amount    = $10,000 × 1% = $100
price_risk     = 2000 - 1990 = $10
units          = $100 / $10 = 10 oz
lots           = 10 / 100,000 = 0.0001 lots  ← UNTRADEABLE (below minimum)
```

**Result:** Position rejected or silently rounded to 0. No trade executed. Strategy appears "inactive."

### After (units_per_lot = 100)

```
risk_amount    = $10,000 × 1% = $100
price_risk     = 2000 - 1990 = $10
units          = $100 / $10 = 10 oz
lots           = 10 / 100 = 0.1 lots  ← VALID (1 mini lot)
```

**Result:** Correct 0.1 lot position. Notional = 10 oz × $2,000 = $20,000. Risk = 10 oz × $10 = $100 (1% of account). ✓

---

## 7. Tests Added

File: `tests/test_units_per_lot_config.py` (85 lines)

| Test class | Test method | What it validates |
|---|---|---|
| `TestPositionSizerReadsConfig` | `test_default_units_per_lot_from_config` (×4 sizers) | All 4 sizer classes read `100.0` from config by default |
| `TestPositionSizerOverride` | `test_fixed_fractional_override` | Explicit `units_per_lot` overrides config |
| `TestPositionSizerOverride` | `test_kelly_override` | Same for KellySizer |
| `TestPositionSizerOverride` | `test_atr_override` | Same for ATRSizer |
| `TestPositionSizerOverride` | `test_anti_martingale_override` | Same for AntiMartingaleSizer |
| `TestRiskEngineUsesConfig` | `test_risk_engine_default` | RiskEngine reads `100.0` from config |
| `TestCalculateCorrectSize` | `test_calculate_gold_sizing` | XAUUSD with 100 produces 0.1 lots (reasonable range) |
| `TestCalculateCorrectSize` | `test_forex_still_works` | EURUSD with explicit 100000 override produces 0.1 lots |

---

## 8. Strategy / Risk / Execution Impact

| Component | Impact | Mitigation |
|---|---|---|
| **Sizers** (FixedFractional, Kelly, ATR, AntiMartingale) | Now default to 100 — correct for XAUUSD | No action needed for gold/CFD strategies |
| **Strategy.calculate_position_size** | Falls back to 100 — correct for CFDs | Forex strategies must pass `units_per_lot=100000` |
| **RiskEngine** | Already used 100 fallback — no change | No action needed |
| **PaperBrokerAdapter** | Commission calculation now uses correct lot divisor | Commissions on XAUUSD now 1000x higher (correct) |
| **Backtest results** | All historical XAUUSD backtests are invalidated | Must be re-run with new default |

---

## 9. Historical Result Invalidation

**ALL historical backtest and shadow-run results for XAUUSD and other non-forex instruments are INVALID.** Positions were sized 1000x too small (or too large if `units_per_lot` was manually set to 100000 for forex-like behavior).

| Artifact category | Status | Required action |
|---|---|---|
| `shadow_results/` XAUUSD runs | INVALIDATED | Re-run required |
| `reports/` backtest reports for gold | INVALIDATED | Re-run required |
| `artifacts/` release gate outputs | CONDITIONALLY VALID | Only forex results remain valid |
| Strategy Sharpe / PnL figures | INVALIDATED | Do not reference in live-readiness decisions |

**Rule:** No backtest or shadow result may be cited as evidence for live readiness if it used `units_per_lot = 100000` for a non-forex instrument.

---

## 10. Rollback Procedure

If this change causes unexpected breakage in live-readiness gating:

1. **Immediate rollback:**
   ```bash
   cd graxia/packages/quant_os
   git revert HEAD --no-edit
   ```

2. **Selective rollback** (revert config only, keep tests):
   ```python
   # core/config.py line 136
   units_per_lot: float = 100000.0  # restore old default
   ```

3. **Verify rollback:**
   ```bash
   python -m pytest tests/test_units_per_lot_config.py -v
   # All tests should FAIL with old default (expected)
   python -m pytest tests/ --tb=short -q
   ```

4. **Notify:** Log rollback in `CONSTITUTION.md` change log with reason.

---

## 11. Gate Status

```
GATE: UNITS_PER_LOT_CHANGE_REVIEW_REQUIRED
STATUS: BLOCKED — requires risk review approval before merge
```

**Blocking conditions:**
- [ ] All 8 tests in `test_units_per_lot_config.py` pass
- [ ] Risk owner approves the default change
- [ ] Forex strategy owners acknowledge need for explicit override
- [ ] Historical backtests for XAUUSD are re-run and re-baselined
- [ ] `risk/engine.py:422` misused `portfolio_value` bug is filed as separate CR

---

*Generated by risk review agent — CR_UNITS_PER_LOT_REMEDIATION*

# Phase 2A: Hardcode Audit Report

**Generated:** 2026-06-20
**Scope:** All `.py` files under `graxia/packages/quant_os/`
**Patterns searched:** `units_per_lot`, `100000`, `pip_value`, `lot_size`, `contract_size`, `tick_value`, `point_value`, `risk_per_trade_pct`, `risk_per_trade_bps`, gold-specific sizing assumptions

---

## Summary

| Category | Count |
|----------|-------|
| MUST_REMOVE_FROM_PRODUCTION | 8 |
| REQUIRES_MANUAL_REVIEW | 6 |
| BACKTEST_FIXTURE_ONLY | 12 |
| TEST_ONLY | 18 |
| DOCUMENTATION_ONLY | 2 |
| ACCEPTABLE (stdlib/contract_spec) | ~20 |

---

## MUST_REMOVE_FROM_PRODUCTION

### 1. `core/config.py:86` — Hardcoded `units_per_lot = 100000.0`
- **Context:** Global config default. Forex assumption (100k units = 1 standard lot).
- **Fix:** Remove default; require symbol-specific lookup from ContractSpec.

### 2. `backtest/engine.py:34` — `BacktestConfig.units_per_lot = 100000.0`
- **Context:** BacktestConfig hardcodes forex lot size. XAUUSD uses 100 oz/lot.
- **Fix:** BacktestConfig should accept per-symbol contract size or remove the field.

### 3. `backtest/engine.py:330` — `pip_value = Decimal("0.01") if "JPY" else Decimal("0.0001")`
- **Context:** `_execute_signal()` default SL fallback uses hardcoded pip values.
- **Fix:** Use ContractSpec.point or reject signals without explicit SL.

### 4. `backtest/engine.py:346` — Same hardcoded pip_value for slippage.
- **Fix:** Same as above.

### 5. `risk/engine.py:85` — `self.units_per_lot = getattr(config, 'units_per_lot', 100000.0)`
- **Context:** RiskEngine defaults to 100k units.
- **Fix:** Require per-symbol contract size lookup.

### 6. `risk/engine.py:169,184,189,216,294,422` — Multiple `portfolio_value = self.units_per_lot` / `order.quantity * self.units_per_lot`
- **Context:** Risk calculations use hardcoded lot size as portfolio proxy. Lines 189, 216, 294 use `units_per_lot` as stand-in for portfolio value (ponytail simplifications).
- **Fix:** These need actual account equity from broker, not `units_per_lot`.

### 7. `execution/broker_adapter.py:177` — `lot_size = Decimal(str(getattr(config, 'units_per_lot', 100000)))`
- **Context:** PaperBroker commission calculation uses hardcoded lot size.
- **Fix:** Use ContractSpec or symbol-specific value.

### 8. `gold_bot/core/engine.py:724-726` — `quantity = risk_amount / (risk_per_unit * 100)` with comment "For gold: 1 lot = 100 oz"
- **Context:** Gold-specific sizing hardcoded in engine.
- **Fix:** Use ContractSpec from MT5.

---

## REQUIRES_MANUAL_REVIEW

### 9. `strategies/base.py:177` — `units_per_lot: float = 100000.0` parameter default
- **Context:** `calculate_position_size()` method accepts units_per_lot with forex default.
- **Fix:** Consider requiring explicit parameter (no default).

### 10. `risk/position_sizer.py:35,109,182,273,337` — `units_per_lot: float = 100000.0` default in all sizers
- **Context:** All position sizers default to 100k. Parameter is overridable.
- **Fix:** Acceptable if callers always pass correct value. Verify all callers.

### 11. `risk/pre_trade_risk.py:14` — `max_risk_per_trade_pct: Decimal = Decimal("1.0")`
- **Context:** Uses percentage-based risk. Task 3 migrates to bps.
- **Fix:** Will be superseded by RiskPolicy in risk_policy.py.

### 12. `gold_bot/core/config.py:35` — `units_per_lot: float = 100.0`
- **Context:** Gold bot correctly defaults to 100 oz/lot for XAUUSD.
- **Fix:** This is correct for gold bot's XAUUSD-only scope. No change needed.

### 13. `execution/broker_adapter.py:249,252` — `pip_value = Decimal("10") if "JPY" else Decimal("1")`
- **Context:** Unrealized P&L calculation in PaperBroker. These are pip multipliers for JPY pairs.
- **Fix:** Review if these represent correct tick value per pip.

### 14. `risk/portfolio.py:22` — `risk_pct: float` field name
- **Context:** PositionExposure.risk_pct is a data field name, not a config.
- **Fix:** Acceptable as-is; field represents computed risk %, not config input.

---

## BACKTEST_FIXTURE_ONLY (acceptable in baseline/test files)

| File | Line(s) | Value | Notes |
|------|---------|-------|-------|
| `tests/baseline_xauusd.py` | 82 | `units_per_lot=100` | XAUUSD baseline fixture |
| `tests/baseline_multi_symbol.py` | 47 | `units_per_lot=100` | Multi-symbol baseline fixture |
| `tests/test_single.py` | 28 | `units_per_lot=100` | Test fixture |
| `tests/test_vwap.py` | 15 | `units_per_lot=100` | Test fixture |
| `tests/test_timing.py` | 41 | `units_per_lot=100` | Test fixture |
| `tests/test_timing2.py` | 33 | `units_per_lot=100` | Test fixture |
| `tests/test_timing3.py` | 42 | `units_per_lot=100` | Test fixture |
| `tests/run_all_13_real.py` | 47 | `units_per_lot=100` | Baseline runner |
| `tests/outofsample_xauusd.py` | 122 | `units_per_lot=100.0` | Out-of-sample test |
| `tests/test_lookahead_regression.py` | 211 | `units_per_lot=100` | Regression test |
| `tests/test_antimartingale_tiers.py` | 28,56,82,108,133 | `units_per_lot=100.0` | Unit test fixtures |
| `run_backtest_real.py` | 30 | `units_per_lot=100000` | Forex backtest runner |

---

## TEST_ONLY (in test files, no production impact)

| File | Line(s) | Value | Notes |
|------|---------|-------|-------|
| `tests/test_position_sizer_numeric.py` | 51,69,84,100,115,116,141 | `units_per_lot` | Sizer unit tests |
| `tests/test_bias_detection_deterministic.py` | 62,104,142,179 | `100000` (volume) | Volume fixture, not sizing |
| `tests/test_bias_detection_real.py` | 46 | `100000` (volume) | Volume fixture |
| `tests/diagnostic_mrb_mlb_real.py` | 32,54 | `100000` (volume) | Volume fixture |
| `tests/test_new_modules.py` | 31 | `100000` (volume) | Volume fixture |
| `tests/test_lookahead_regression.py` | 102 | `100000` (volume) | Volume fixture |

---

## DOCUMENTATION_ONLY

| File | Line(s) | Notes |
|------|---------|-------|
| `tests/test_position_sizer_numeric.py` | 4,46 | Docstring mentions `units_per_lot` |
| `gold_bot/core/engine.py` | 724 | Comment: "For gold: 1 lot = 100 oz" |

---

## ACCEPTABLE (stdlib / contract_spec pattern)

These use `ContractSpec` or `trade_contract_size` / `trade_tick_value` from MT5 — no hardcoding:

- `broker/mt5_gateway.py` — Reads from MT5 symbol_info()
- `broker/contract_spec.py` — Stores broker-provided values
- `broker/contract_snapshot_store.py` — Persists ContractSpec snapshots

---

## Key Findings

1. **`units_per_lot` is the dominant hardcode risk.** 58 occurrences found. Most in test files (acceptable), but core config, engine, and risk engine all default to 100k.
2. **`pip_value` hardcoding in `backtest/engine.py`** is the second-highest risk. Only handles JPY vs non-JPY, doesn't account for XAUUSD pip value ($0.01 per pip vs $0.0001 for forex).
3. **`risk/engine.py` uses `units_per_lot` as a proxy for portfolio value** in 3 places — this is incorrect and will produce wrong risk calculations.
4. **`gold_bot/core/engine.py` hardcodes "1 lot = 100 oz"** — correct for XAUUSD but not parameterized.
5. **All `_pct` risk fields are consistently used** — the bps migration in Task 3 will address this cleanly.

---

## Recommendations

1. **Immediate:** Add `ponytail:` comments to all `MUST_REMOVE_FROM_PRODUCTION` items marking them for Phase 2B.
2. **Phase 2B:** Replace all `units_per_lot` defaults with ContractSpec lookup. Require per-symbol sizing at every layer.
3. **Phase 2B:** Replace hardcoded `pip_value` in backtest engine with ContractSpec.point.
4. **Phase 2B:** Fix `risk/engine.py` portfolio_value to use actual account equity.

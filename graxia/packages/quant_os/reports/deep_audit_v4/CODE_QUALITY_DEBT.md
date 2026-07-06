# CODE QUALITY & TECHNICAL DEBT — Phase 18
**Date:** 2026-07-05
**Auditor:** Strategist Agent
**Scope:** God functions/files, duplicated logic, hardcoded parameters, error handling, circular deps, type safety, test coverage inversion
**Status:** READ-ONLY — no modifications made

---

## 18.1 God Functions & God Files

### Finding: Large orchestration scripts (>500 lines)

| File | Lines | Purpose | Risk |
|------|-------|---------|------|
| `scripts/train_live_model.py` | 784 | Train XGBoost+LightGBM+CatBoost ensemble | Monolithic — combines data loading, feature selection, Optuna tuning, 3 model training, ensemble, saving |
| `scripts/train_mega_model_v2.py` | 734 | Same as above with v2 improvements | Same risks — copies large portions of train_live_model.py |
| `scripts/train_mega_model.py` | 679 | Same as above, original version | Triple overlap with above two |
| `core/trading_loop.py` | 535 | Brain stem of execution system | Large but well-structured with clear sections |
| `ml/pipeline.py` | 560 | Feature engineering + training + drift | Multiple concerns in one file |
| `ml/drift_monitor.py` | 580 | Full-featured drift detection | Reasonable for single responsibility |
| `backtest/engine.py` | ~1200+ | Core backtest engine | Largest single file — multiple responsibilities |

### Finding: FeatureEngineer.generate_features() is 160+ lines

`ml/pipeline.py:68-226` — 158 lines of feature generation in a single method. Computes 30+ features (returns, EMAs, RSI, MACD, Bollinger, ATR, ADX, volume, volatility, candle patterns, stochastic). **Hard to test individual features; hard to extend without breaking.**

### Finding: train_model_pipeline() is 170+ lines

`train_live_model.py:480-650` — combines data prep, feature selection, Optuna tuning (3 separate model types), model training (3 models), ensemble voting, walk-forward CV, feature importance aggregation, and metric reporting. **Violates single responsibility.**

| Severity | Finding | Evidence |
|----------|---------|----------|
| MEDIUM | 7 files >500 lines; 3 training scripts heavily overlapping | `train_live_model.py` (784), `train_mega_model_v2.py` (734), `train_mega_model.py` (679) |
| MEDIUM | FeatureEngineer.generate_features() at 158 lines | `ml/pipeline.py:68-226` |
| LOW | train_model_pipeline() at 170 lines | `train_live_model.py:480-650` |

---

## 18.2 Duplicated Logic

### Finding: THREE separate drift detector implementations

| Implementation | File | Lines | Features |
|---------------|------|-------|----------|
| `DriftDetector` | `ml/pipeline.py:509-560` | 51 | Accuracy drop over rolling window |
| `DriftMonitor` | `ml/drift_monitor.py:65-580` | 515 | Accuracy + PSI + staleness + DuckDB persistence |
| `check_drift()` | `scripts/auto_retrain.py:112-167` | 55 | Recent vs historical accuracy split |

**All three compute accuracy-based drift but use different window sizes, splits, and thresholds.** None delegate to another.

### Finding: TWO separate feature engineering implementations

| Implementation | File | Lines | Features |
|---------------|------|-------|----------|
| `FeatureEngineer.generate_features()` | `ml/pipeline.py:68-226` | 158 | 30+ features via pandas_ta |
| `build_features()` | `scripts/train_all_models.py:47-74` | 27 | 17 manual features (different computation) |

**These produce DIFFERENT feature sets with DIFFERENT names.** `train_all_models.py` does NOT use `FeatureEngineer` — it computes features inline with manual formulas.

### Finding: THREE training scripts with duplicated Optuna + model training logic

`train_live_model.py`, `train_mega_model.py`, and `train_mega_model_v2.py` all independently implement:
- `walk_forward_cv()` for Optuna inner loop
- `make_xgb_objective()`, `make_lgb_objective()`, `make_cb_objective()`
- `train_xgboost()`, `train_lightgbm()`, `train_catboost()`
- `soft_vote_ensemble()`
- `compute_trading_metrics()`
- `load_data()`, `get_live_features()`, `select_features_mi()`

**~500 lines duplicated across 3 files.** The `v2` file has comments like "Changes from v1: regularized hyperparameters" but didn't refactor shared code.

### Finding: TWO signal prediction paths

`ml/pipeline.py:MLTrainer.predict()` at `:454` and `ml/pipeline.py:MLTrainer.predict_payload()` at `:478` — predict_payload wraps predict but duplicates vectorization logic (line 468-469 same pattern as 461-462 in predict).

### Finding: Cost model duplication (prior audit finding, unverified)

The `CORRECTIVE_AUDIT_ADDENDUM.md:48-118` documents THREE cost paths:
1. `backtest/engine.py` — hardcoded costs
2. `scripts/backtest_cost.py` — different hardcoded costs
3. `scripts/walk_forward.py` — third set from `config/cost_calibration.json`

Same finding from Phase 8 — still not consolidated.

| Severity | Finding | Evidence |
|----------|---------|----------|
| HIGH | Three drift detector implementations | `ml/pipeline.py:509`, `ml/drift_monitor.py:65`, `auto_retrain.py:112` |
| HIGH | Two incompatible feature engineering implementations | `ml/pipeline.py:68` vs `train_all_models.py:47` |
| HIGH | ~500 lines duplicated across 3 training scripts | `train_live_model.py`, `train_mega_model.py`, `train_mega_model_v2.py` |
| HIGH | Three incompatible cost calculation paths (prior P1) | Per corrective audit — still unresolved |

---

## 18.3 Hardcoded Parameters

### Finding: Trading costs hardcoded in engine.py

Per `CORRECTIVE_AUDIT_ADDENDUM.md:52-56`:
```python
engine.py:437  → spread = Decimal("0.01") * Decimal("2")  # HARDCODED 2 pips
engine.py:92   → commission_per_lot: Decimal = Decimal("3.5")  # HARDCODED $3.5
engine.py:91   → slippage_pips: float = 0.5  # HARDCODED 0.5 pips
```

### Finding: ML hyperparameters hardcoded across scripts

| Parameter | Value | Files |
|-----------|-------|-------|
| `n_estimators=200` | Fixed | `train_all_models.py:135`, `ml/pipeline.py:419` |
| `max_depth=3` | Fixed | `train_all_models.py:136`, `ml/pipeline.py:420` |
| `learning_rate=0.01` | Fixed | `train_all_models.py:137`, `ml/pipeline.py:421` |
| `DRIFT_THRESHOLD=0.10` | Fixed | `auto_retrain.py:42` |
| `MIN_SAMPLES=500` | Fixed | `auto_retrain.py:43` |
| `EMBARGO=12` | Fixed | Multiple training scripts |
| `RANDOM_STATE=42` | Fixed | Universal |
| `DEFAULT_BATCH_SIZE=1000` | Fixed | `data/duckdb_write_queue.py:35` |

### Finding: Symbol-to-asset-class mapping hardcoded

`core/trading_loop.py:51-72` — `_SYMBOL_ASSET_CLASS` dict with 22 hardcoded mappings. Adding a new symbol requires code change.

### Finding: Instrument-specific values hardcoded

```python
# trading_loop.py:137-138
if symbol.upper() == "XAUUSD":
    pip_value = 0.01  # Hardcoded for gold

# pipeline.py:177
_annualize_1h = np.sqrt(252 * 23)  # Hardcoded annualization for 1H bars

# auto_retrain.py:42
DRIFT_THRESHOLD = 0.10  # 10% accuracy drop
```

### Finding: Symbol list hardcoded

`train_all_models.py:43`: `SYMBOLS = ["XAUUSD", "EURUSD", "US30", "NAS100", "BTCUSD"]`

`train_live_model.py:63-89`: `LIVE_FEATURES` list and `EXCLUDE_COLS` set — 87+ hardcoded feature names.

| Severity | Finding | Evidence |
|----------|---------|----------|
| MEDIUM | Trading costs hardcoded in engine.py | Spread=2 pips, slippage=0.5 pips, commission=$3.5 |
| MEDIUM | ML hyperparameters hardcoded in multiple files | See table above |
| LOW | Symbol mappings and annualization factors hardcoded | `trading_loop.py:51-72`, `pipeline.py:177` |

---

## 18.4 Error Handling

### Finding: 13 bare `except:` clauses in scripts

All 13 bare excepts are in `scripts/` or root-level quality check files. **Zero bare excepts in `core/`, `risk/`, `execution/`, `backtest/`, or `ml/` modules.** Production paths properly use `except Exception as e:`.

### Finding: event_bus.py swallows handler errors — by design

`core/event_bus.py:131-142`:
```python
for handler in handlers:
    try:
        handler(event)
    except Exception as e:
        self._handler_errors += 1
        logger.error(...)
```
This is the correct pattern for an event bus — one bad handler should not crash others.

### Finding: duckdb_write_queue.py has careful error handling

`data/duckdb_write_queue.py:186-208` handles queue overflow with drop-oldest policy, logging every drop. Writer loop at `:226-249` catches `asyncio.CancelledError` separately from general exceptions.

### Finding: Trading loop has comprehensive rejection logging

`core/trading_loop.py:240-305` rejects signals with explicit reasons:
- No stop loss (`:245-252`)
- Daily order limit exceeded (`:256-274`)
- Invalid entry/SL/TP levels (`:278-287`)
- SL on wrong side of entry (`:289-297`)
- Zero quantity (`:301-305`)

All rejections are logged at WARNING level — **generously readable audit trail.**

### Finding: kill_switch.py crash-safety still an open P0 (v3)

Per `AUDIT_INDEX.md:25`: "BUG-KILL: Kill switch silently resets to OFF on corrupt JSON (`risk/kill_switch.py:149-151`)" — this v3 P0 is not addressed in v4.

| Severity | Finding | Evidence |
|----------|---------|----------|
| LOW | 13 bare excepts in non-critical scripts | `scripts/` — see 17.4 for list |
| PASS | Production error handling is proper | EventBus, TradingLoop, DuckDBWriter all handle exceptions correctly |
| PASS | Trading loop rejection logging is comprehensive | `core/trading_loop.py:240-305` |
| HIGH | Kill switch crash-safety still open v3 P0 | `AUDIT_INDEX.md:25` — not in v4 P0 list |

---

## 18.5 Circular Dependencies

### Finding: No circular imports detected

The codebase uses flat import patterns. Core modules import from each other minimally:
- `core/event_bus.py` imports from `core/events.py`
- `core/trading_loop.py` imports from `core/event_bus.py`, `core/events.py`, `core/enums.py`, `core/golden_rules.py`
- `ml/pipeline.py` imports from `core/safe_pickle.py`
- `ml/drift_monitor.py` has no cross-module imports to core/ml

**No circular dependency chains detected.** The import graph appears acyclic.

| Severity | Finding |
|----------|---------|
| PASS | No circular imports detected |

---

## 18.6 Backtest / Live Code Sharing

### Finding: Shared feature computation — import-tested

Per Phase 8 findings in `AUDIT_INDEX.md:44`: "Feature computation shared" — the backtest and live paths share feature modules. However, the `CORRECTIVE_AUDIT_ADDENDUM.md` identified that fill model diverges between paths.

### Finding: FeatureEngineer used in both backtest and auto-retrain

`scripts/auto_retrain.py:29`: `from ml.pipeline import FeatureEngineer` — uses canonically shared feature computation.

### Finding: Live bot may use DIFFERENT features

`scripts/train_live_model.py:63-89` defines `LIVE_FEATURES` — a subset of features computable from OHLCV only (no cross-asset, macro, COT features). The paper trading bot loads `xgboost_live_*.pkl` which was trained on these LIVE_FEATURES. **This is good — the bot features match training features.** But there is no automated verification.

| Severity | Finding | Evidence |
|----------|---------|----------|
| MEDIUM | Feature module shared but no automated parity test | `auto_retrain.py:29` imports FeatureEngineer from `ml/` |
| LOW | Live features subset manually curated, not auto-verified | `train_live_model.py:63-89` |

---

## 18.7 Type Safety

### Finding: Type hints used extensively in core modules — GOOD

`ml/model_registry.py` — full type hints throughout (dataclasses, `str | Path | None`, `dict[str, Any]`)
`ml/drift_monitor.py` — full type hints
`core/trading_loop.py` — full type hints
`core/event_bus.py` — full type hints
`data/duckdb_write_queue.py` — full type hints

### Finding: Scripts have weaker type coverage

`train_all_models.py` — no type hints beyond function signatures in pandas operations
`train_live_model.py` — has type hints on function signatures
`auto_retrain.py` — has type hints (uses `from __future__ import annotations`)

### Finding: Some `Any` usage in critical paths

```python
# core/trading_loop.py:188
oms: Any | None = None

# ml/pipeline.py:89
model: Any

# ml/model_registry.py:89
model: Any
```

`Any` for `model` is unavoidable (deserialized) but `oms: Any` in trading_loop is a symptom of missing abstract interface.

### Finding: No Python 2/3 division issues

All files use Python 3 syntax exclusively. No `from __future__ import division` in old code.

| Severity | Finding | Evidence |
|----------|---------|----------|
| PASS | Core modules fully type-hinted | model_registry, drift_monitor, trading_loop, event_bus |
| LOW | Scripts have weaker type coverage | train_all_models.py minimal hints |
| LOW | `Any` type for OMS in trading loop — missing interface | `trading_loop.py:188` |

---

## 18.8 Test Coverage vs Risk Concentration

### Risk-Consequence Ranking (highest consequence first):

| Rank | Module | Consequence of Failure | Known Coverage |
|------|--------|----------------------|----------------|
| 1 | `risk/kill_switch.py` | Catastrophic — uncontrolled losses | test_chaos, test_phase_9 |
| 2 | `core/trading_loop.py` | Critical — sends real orders | test_phase_3b_native |
| 3 | `execution/adapters/mt5.py` | Critical — live order submission | Limited (requires MT5 terminal) |
| 4 | `backtest/engine.py` | High — all strategy validation | Extensive test coverage |
| 5 | `risk/pre_trade_risk.py` | High — risk gate bypass | test_phase_2b |
| 6 | `ml/pipeline.py` | High — signal quality | test_ml_pipeline_training |
| 7 | `ml/model_registry.py` | Medium — model audit trail | Only 2 test files |
| 8 | `ml/drift_monitor.py` | Medium — drift detection | test_chaos |
| 9 | `core/event_bus.py` | Medium — system communication | Indirect through integration tests |
| 10 | `validation/decay_monitor.py` | Low — monitoring only | Only test_phase4_wiring |

### Inversion Check:

| Concern | Consequence Rank | Coverage Rank | Inverted? |
|---------|-----------------|---------------|-----------|
| Kill switch | 1 (highest) | Medium | **Yes — HIGH** |
| Live execution (MT5Adapter) | 3 | Low (needs MT5) | Yes — unavoidable |
| Backtest engine | 4 | High | No |
| Model training (pipeline.py) | 6 | Medium | No |
| Decay monitor | 10 (lowest) | Low | No |

**The main inversion is kill_switch.py** — highest consequence (uncontrolled losses) but crash-safety bug is a KNOWN v3 P0 not yet fixed. The test suite likely doesn't test the crash-corruption scenario.

| Severity | Finding | Evidence |
|----------|---------|----------|
| HIGH | Kill switch is highest-consequence, medium-coverage, open P0 | `risk/kill_switch.py:149-151` — crash-corruption bug unfixed per v3 |
| MEDIUM | MT5Adapter untestable without live MT5 terminal | `execution/adapters/mt5.py` |

---

## Summary: Phase 18 — Code Quality

| Area | Status | Top Issue |
|------|--------|-----------|
| God Functions/Files | PARTIAL | 3 training scripts with ~500 lines of duplication |
| Duplicated Logic | FAIL | 3 drift detectors, 2 feature engines, 3 training pipelines |
| Hardcoded Parameters | PARTIAL | Trading costs, ML hyperparams, instrument-specific values |
| Error Handling | PASS | Production paths proper; 13 bare excepts only in scripts |
| Circular Dependencies | PASS | No circular imports |
| Backtest/Live Code Sharing | PARTIAL | Shared but not parity-tested |
| Type Safety | PASS | Core modules fully typed; scripts weaker |
| Test Coverage Inversion | FAIL | Kill switch is highest-consequence, open-P0, medium-coverage |

### Top 3 P0/P1 Findings:
1. **Drift detection duplicated 3x** — `ml/pipeline.py:509`, `ml/drift_monitor.py:65`, `auto_retrain.py:112` — none interoperate
2. **Feature engineering duplicated 2x** — `ml/pipeline.py:68` vs `train_all_models.py:47` — produce incompatible feature sets
3. **~500 lines duplicated across 3 training scripts** — `train_live_model.py`, `train_mega_model.py`, `train_mega_model_v2.py`

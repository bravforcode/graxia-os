# MODEL LIFECYCLE AUDIT — Phase 16
**Date:** 2026-07-05
**Auditor:** Strategist Agent
**Scope:** ML model identity, training, retraining, drift detection, reproducibility
**Status:** READ-ONLY — no modifications made

---

## 16.1 Model Identity & Versioning

### Finding: Model Registry exists but is UNUSED

`ml/model_registry.py` (385 lines) provides a full `ModelRegistry` class with:
- Unique version IDs (`{model_name}_{timestamp}_{short_uuid}`)
- JSON metadata sidecars alongside `.pkl` artifacts
- Registry index (`registry_index.json`)
- Model comparison, listing, deletion, tag filtering

**However, `ml/models/registry_index.json` does NOT exist.** No training script uses `ModelRegistry.register_model()`. The only imports of `ModelRegistry` are in TWO test files:
- `tests/chaos/test_risk_monitoring_ml_untested.py:1804,2023`
- `tests/test_ml_pipeline_training.py:324`

### Finding: Models versioned by timestamp only, no hash

All training scripts save models with timestamp-based filenames:
- `train_all_models.py:195`: `pickle.dump(..., f"xgboost_{symbol}_{timestamp}.pkl")`
- `ml/pipeline.py:318`: `version = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")`
- `train_live_model.py:689`: `pickle.dump(..., f"mega_xgboost_live_{TIMESTAMP}.pkl")`
- `run_ml_train.py`: Uses `MLTrainer.train()` which saves to `{model_type}_{version}.pkl`

**No content hash (SHA-256) of the trained model artifact is computed or stored.** Timestamps uniquely identify but do not cryptographically guarantee identity.

### Finding: Live system does NOT log model hash per signal

`ml/pipeline.py:MLTrainer.predict_payload()` at `:496` extracts model version from filename:
```python
model_version = model_path.split("/")[-1].replace(".pkl", "")
```
This is a filename-based version string, not a hash. If a model file is silently overwritten (same filename), the system cannot detect the change.

### Finding: 37 unversioned model files in ml/models/

```
xgboost_XAUUSD_20260626.pkl          (no timestamp seconds — older naming)
xgboost_XAUUSD_20260626_160329.pkl
xgboost_XAUUSD_20260703_124417.pkl
xgboost_live_20260626.pkl
xgboost_live_20260626_143317.pkl
... (12 xgboost_live variants for 20260626)
xgboost_live_20260627_130006.pkl
xgboost_US30/NAS100/EURUSD/BTCUSD variants
xgboost_v3_* variants
```

No JSON metadata sidecars. No registry index. **37 pickle files are the ONLY records.**

| Severity | Finding | Evidence |
|----------|---------|----------|
| HIGH | ModelRegistry unused — models unversioned | `ml/model_registry.py` exists; `registry_index.json` absent; no training script calls `register_model()` |
| HIGH | No content hash for model identity | No SHA-256/MD5 stored in any model file or manifest |
| MEDIUM | Signal does not carry hash-locked model version | `ml/pipeline.py:496` uses filename not hash |

---

## 16.2 Training/Validation Discipline

### Finding: CPCV with purging (train_all_models.py) — GOOD

`scripts/train_all_models.py:104-118` uses purged combinatorial cross-validation:
```python
paths = combine_purged_k_fold_cv(
    n_bars=n_bars, n_splits=6, n_test_splits=2,
    purged_size=12, embargo_size=12, random_state=42,
)
```
This is the best-practice cross-validation pattern in the codebase. **However, there is no inner-loop hyperparameter tuning** — hyperparameters are hardcoded (`n_estimators=200, max_depth=3, learning_rate=0.01`). The CPCV is used for EVALUATION only, not nested tuning.

### Finding: Optuna tuning + walk-forward CV (train_live_model.py) — GOOD

`scripts/train_live_model.py:247-273` uses Optuna with inner walk-forward CV:
```python
for train_idx, test_idx in walk_forward_cv(len(X), n_folds=3, embargo=12):
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)])
```
This properly separates tuning (inner loop) from evaluation (outer 80/20 split at `:511`). **This is the correct nested CV pattern.** However, final evaluation is a single 80/20 split — no repeated outer splits.

### Finding: Simple train_test_split in ml/pipeline.py — WEAK

`ml/pipeline.py:282-287` uses a plain temporal split:
```python
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, shuffle=False,
)
```
No purging, no embargo, no cross-validation folds. This is inadequate for financial time series.

### Finding: run_ml_train.py uses same weak split

`run_ml_train.py:79`: Single `train(feature_set, test_ratio=0.2)` — no CV at all.

### Finding: Multiple training scripts with inconsistent methodology

| Script | CV Method | HP Tuning | Nested CV? | Purged? |
|--------|-----------|-----------|------------|---------|
| `train_all_models.py` | CPCV (6×2) | Fixed | No | Yes |
| `train_live_model.py` | Walk-forward 3-fold (Optuna) + 80/20 | Optuna | Yes | Embargo=12 |
| `train_mega_model.py` | Walk-forward 3-fold (Optuna) + 80/20 | Optuna | Yes | Embargo=12 |
| `train_mega_model_v2.py` | Walk-forward CV | Optuna | Yes | Embargo=24 |
| `ml/pipeline.py:MLTrainer` | Plain 80/20 split | Fixed | No | No |
| `run_ml_train.py` | Plain 80/20 split | Fixed | No | No |
| `auto_retrain.py` | Walk-forward 3 windows | Fixed | No | No |

**Three different cross-validation methodologies producing incompatible model evaluations.**

| Severity | Finding | Evidence |
|----------|---------|----------|
| MEDIUM | train_all_models uses CPCV but no inner HP tuning | `train_all_models.py:134-146` hardcoded `max_depth=3, learning_rate=0.01` |
| MEDIUM | ml/pipeline.py uses plain 80/20 split — no CV | `ml/pipeline.py:282-287` |
| LOW | Six training scripts with inconsistent CV methodology | See table above |

---

## 16.3 Retraining Cadence & Staleness

### Finding: auto_retrain.py exists but is manual/loop-based

`scripts/auto_retrain.py:1-10`:
```
python scripts/auto_retrain.py          # one-shot check
python scripts/auto_retrain.py --loop   # continuous (every 1h)
python scripts/auto_retrain.py --force  # force retrain
```

The `--loop` mode runs `await asyncio.sleep(args.interval)` (default 3600s). It uses its own standalone `check_drift()` and `retrain_model()` — **NOT** `ml/drift_monitor.py::DriftMonitor` and **NOT** `ml/model_registry.py::ModelRegistry`.

### Finding: Three independent drift detection implementations

| Component | File | Method | Wired to auto-retrain? |
|-----------|------|--------|----------------------|
| `DriftDetector` | `ml/pipeline.py:509-560` | Accuracy drop over rolling window | No |
| `DriftMonitor` | `ml/drift_monitor.py:65-580` | PSI + accuracy + staleness + DuckDB persistence | No (only in `api/signal_service.py:521`) |
| `check_drift()` | `scripts/auto_retrain.py:112-167` | Recent vs historical accuracy split | Standalone |

**None of these three are wired together.** The auto_retrain.py uses its own logic. The DriftMonitor (most sophisticated) is only used in signal_service for reporting, NOT for triggering retrain.

### Finding: core/lifecycle.py does NOT coordinate retrain

`core/lifecycle.py:7-32` is a simple ABC mixin with lifecycle hooks (`bot_start`, `bot_loop_start`, `confirm_trade_entry`, etc.). It has no retrain-triggering logic, no drift check, no model staleness check. The comment "Strategy lifecycle hooks from Freqtrade pattern" confirms it is a FreqTrade-compatible pattern adapter, not a retrain coordinator.

### Finding: champion.pkl hot-swap pattern

`auto_retrain.py:45`: `CHAMPION_PATH = MODEL_DIR / "champion.pkl"` — uses a "champion/challenger" pattern. `hot_swap()` at `:85-100` compares challenger to champion by deflated Sharpe and max drawdown. **However, `evaluate_model()` at `:73-82` returns hardcoded dummy values:**
```python
def evaluate_model(model_data: dict):
    @dataclass
    class ModelMetrics:
        deflated_sharpe: float = 1.0
        oos_max_drawdown: float = 10.0
    return ModelMetrics()
```
This means EVERY model gets `deflated_sharpe=1.0, oos_max_drawdown=10.0` — the comparison is MEANINGLESS. The champion will always be replaced by the first challenger.

### Finding: No staleness monitoring wired to live path

`ml/drift_monitor.py::_check_staleness()` at `:354` checks if predictions have stopped for >4 hours. But this is only called from `check_drift()` which is only called from `api/signal_service.py:521`. **No staleness check runs in the main trading loop, paper bot, or orchestrator.**

| Severity | Finding | Evidence |
|----------|---------|----------|
| CRITICAL | `evaluate_model()` returns hardcoded dummy values — champion selection broken | `auto_retrain.py:73-82` |
| HIGH | Three separate drift detectors, none wired to auto-retrain trigger | `ml/pipeline.py:509`, `ml/drift_monitor.py:65`, `auto_retrain.py:112` |
| HIGH | DriftMonitor not wired to trading loop or orchestrator | Only imported in `api/signal_service.py:521` |
| MEDIUM | core/lifecycle.py does not coordinate retrain | `core/lifecycle.py:7-32` — ABC mixin only |
| MEDIUM | No staleness check in live trading path | `drift_monitor.py:354` only called from signal_service |

---

## 16.4 Input Drift Detection

### Finding: PSI-based feature drift in DriftMonitor (unwired)

`ml/drift_monitor.py::_compute_feature_psi()` at `:419-485` computes Population Stability Index using bin-based normal distribution approximation. It tracks per-feature PSI scores and emits alerts when PSI > threshold (default 0.25). **However, this is only used in the API signal service, not in the trading loop.**

### Finding: FeatureStore exists but minimal

`ml/feature_store.py` — present in the module but unused by any training or live script.

### Finding: No KS-test or mean/variance tracking in live path

The `validation/decay_monitor.py` tracks 8 strategy decay metrics (rolling Sharpe, IR, win rate, signal half-life, etc.) but is purely backward-looking (performance metrics), NOT forward-looking input drift detection. It is only imported in tests.

| Severity | Finding | Evidence |
|----------|---------|----------|
| MEDIUM | PSI-based input drift not wired to live trading | `ml/drift_monitor.py:419` — only in signal_service |
| MEDIUM | FeatureStore unused | `ml/feature_store.py` exists but no imports |
| LOW | No forward-looking input drift in live path | `validation/decay_monitor.py` only in tests |

---

## 16.5 Reproducibility of Exact Live Model

### Finding: Random seeds fixed but non-deterministic behaviors remain

All training scripts use `random_state=42` or `RANDOM_STATE=42`. However:
- **XGBoost with `n_jobs=-1`** (`train_live_model.py:268`) is NOT fully deterministic even with fixed `random_state`. Thread scheduling affects floating-point accumulation order in tree building. To be deterministic, `nthread=1` and `tree_method='hist'` must be set.
- **LightGBM with `n_jobs=-1`** (`train_live_model.py:358`) has the same issue — thread parallelism introduces non-deterministic floating-point reduction.
- **CatBoost** is deterministic with `random_seed` but uses internal parallelism.

### Finding: No byte-for-byte reproducibility test

`scripts/verify_reproducibility.py:1-23` only checks CSV file SHA-256 hashes:
```python
h = hashlib.sha256(csv.read_bytes()).hexdigest()
print(f"{csv.name}: {h[:16]}")
```
This verifies INPUT data integrity, NOT model reproducibility. **There is no test that trains a model twice and compares outputs.**

### Finding: pandas_ta indicators could vary across versions

`ml/pipeline.py:86`: `import pandas_ta as ta` — indicator library. Different versions of pandas_ta could produce slightly different indicator values (e.g., RSI normalizations, EMA initializations).

### Finding: Optuna sampling introduces randomness

`train_live_model.py:531`: `sampler=TPESampler(seed=RANDOM_STATE)` — TPE sampler uses `seed` which makes sampling reproducible within the SAME Optuna version. Different Optuna versions could sample differently.

| Severity | Finding | Evidence |
|----------|---------|----------|
| HIGH | XGBoost with n_jobs=-1 is non-deterministic | `train_live_model.py:268` sets `n_jobs=-1` without `nthread=1` |
| MEDIUM | LightGBM with n_jobs=-1 is non-deterministic | `train_live_model.py:358` |
| MEDIUM | No byte-for-byte reproducibility test exists | `verify_reproducibility.py:1-23` — CSV hash only |
| LOW | pandas_ta version sensitivity | `ml/pipeline.py:86` — no version pin |

---

## 16.6 Retrain-Automation Audit

### Finding: Drift detection is NOT wired to automated retrain

**The complete chain is broken at every link:**

1. `ml/drift_monitor.py::DriftMonitor` — full-featured drift detection (PSI + accuracy + staleness)
2. `ml/pipeline.py::DriftDetector` — simpler accuracy-based detector
3. `scripts/auto_retrain.py::check_drift()` — standalone, uses its own logic, NOT DriftMonitor
4. `scripts/auto_retrain.py::retrain_model()` — retrains independently, NOT using ModelRegistry
5. `core/lifecycle.py` — provides lifecycle hooks but does NOT wire retrain

**The expected flow would be: DriftMonitor detects drift → triggers auto_retrain → retrains via ModelRegistry → updates champion.** None of these connections exist.

### Finding: auto_retrain.py must be run manually or via cron

`auto_retrain.py:12-13`: "Usage: python scripts/auto_retrain.py" — the only automation is the `--loop` flag with `asyncio.sleep(3600)`. There is no systemd timer, no cron job defined, no external scheduler wiring.

| Severity | Finding | Evidence |
|----------|---------|----------|
| CRITICAL | Drift→Retrain chain completely unwired | DriftMonitor not connected to auto_retrain; auto_retrain uses its own drift check |
| HIGH | No automated retrain scheduler beyond --loop flag | `auto_retrain.py:239-247` — only asyncio.sleep |

---

## 16.7 Drift-Threshold Validation Audit

### Finding: All drift thresholds are arbitrary hardcoded values

| Threshold | File | Value | Justification |
|-----------|------|-------|---------------|
| Accuracy drop | `auto_retrain.py:42` | 0.10 (10%) | No calibration evidence |
| Accuracy threshold | `drift_monitor.py:84` | 0.45 | No calibration evidence |
| PSI threshold | `drift_monitor.py:85` | 0.25 | Industry standard (0.25 = significant) |
| Stale hours | `drift_monitor.py:86` | 4.0 | Arbitrary |
| Accuracy threshold (simple) | `ml/pipeline.py:514` | 0.10 | Arbitrary |

**None of these thresholds have been validated against actual out-of-sample performance degradation.** The relationship between "PSI > 0.25 for feature X" and "strategy PnL degrades by Y%" is completely unknown.

| Severity | Finding | Evidence |
|----------|---------|----------|
| HIGH | All drift thresholds unvalidated against OOS degradation | No calibration study exists; all thresholds are arbitrary constants |
| LOW | Auto-retrain evaluate_model() returns hardcoded dummy values | `auto_retrain.py:73-82` — see 16.3 |

---

## Summary: Phase 16 — Model Lifecycle

| Area | Status | Top Issue |
|------|--------|-----------|
| Model Identity & Versioning | FAIL | ModelRegistry unused; no hash-based identity |
| Training/Validation | PARTIAL | CPCV in train_all_models is good; ml/pipeline.py uses weak 80/20 split |
| Retraining Cadence | FAIL | Champion evaluation broken (dummy values); auto-retrain manual only |
| Input Drift Detection | PARTIAL | DriftMonitor has PSI but unwired to live path |
| Reproducibility | PARTIAL | Seeds fixed but XGBoost/LightGBM with n_jobs=-1 non-deterministic |
| Retrain Automation | FAIL | Drift→Retrain chain completely broken |
| Drift Thresholds | FAIL | All thresholds arbitrary, unvalidated against OOS degradation |

### Top 3 P0 Findings:
1. **`evaluate_model()` returns dummy values** — champion/challenger hot-swap is meaningless (`auto_retrain.py:73-82`)
2. **ModelRegistry exists but is NEVER used** — no versioned model identity (`ml/model_registry.py` vs all training scripts)
3. **Drift→Retrain chain is completely broken** — three separate drift detectors, none trigger retrain; auto_retrain.py runs independently

# Wave 5: ML and Feature Rebuild — Verification Report

Date: 2026-07-02
Status: **COMPLETE** (all tasks pre-existing, 2 test bugs fixed)

## Task 5.1: Build features_v3

### add_technical_features(df)
- **File**: `scripts/build_features_v3_multi_asset.py` (lines 253-315)
- **Status**: Already implemented
- **Features computed**:
  - RSI 14 (period=14)
  - MACD (12, 26, 9) — macd, macd_signal, macd_hist
  - Bollinger Band width (20, 2σ) — bb_width
  - ATR ratio (ATR14 / close)
  - ADX (14)
  - Distance from MA 20, 50, 200 — dist_ma_20, dist_ma_50, dist_ma_200
- **Lookahead safety**: All use rolling/EWM windows on past/current data only

### features_v3_list.md
- **File**: `reports/mega_plan_evidence/features_v3_list.md`
- **Status**: Already exists (72 lines)
- **Content**: Full feature inventory across 5 blocks (SMC, Technical, FRED, COT, Categorical)
- **Total**: ~54 features

## Task 5.2: Purged+embargoed CV

### validation/walk_forward.py
- **File**: `validation/walk_forward.py` (63 lines)
- **Status**: `embargo_bars=12` already set as default
- **Function**: `walk_forward_split(n_bars, n_folds=5, train_ratio=0.7, embargo_bars=12)`

### scripts/train_all_models.py
- **File**: `scripts/train_all_models.py` (170 lines)
- **Status**: Already uses CPCV from `core.cross_validation`
- **No `iloc[:split]`**: Uses `combine_purged_k_fold_cv()` with purged_size=12, embargo_size=12

## Task 5.3: Early stopping

### ml/pipeline.py
- **File**: `ml/pipeline.py` (lines 290-298)
- **Status**: Already implemented
- **XGBoost**: `early_stopping_rounds=10`, `eval_metric="mlogloss"/"logloss"`, `eval_set=[(X_test, y_test)]`
- **Multi-class aware**: Detects n_classes and selects correct eval_metric

### ml/model_registry.py
- **File**: `ml/model_registry.py` (lines 43-45)
- **Status**: Fields already present in `ModelMetadata`:
  - `random_seed: int = 42`
  - `feature_list_hash: str = ""`
  - `dataset_manifest_hash: str = ""`
- **register_model()**: Accepts all three fields as kwargs

## Task 5.4: Multiple testing

### validation/multiple_testing.py
- **File**: `validation/multiple_testing.py` (111 lines)
- **Status**: Already implemented
- **Function**: `benjamini_hochberg(p_values, alpha=0.05)` — BH FDR correction
- **Also includes**: `deflated_sharpe_ratio()` for selection bias correction

## Task 5.5: ML test suite

### tests/test_ml_pipeline_training.py
- **File**: `tests/test_ml_pipeline_training.py` (488 lines)
- **Status**: All 6 required tests present and passing
- **Test classes**:
  1. `TestFeatureSchemaMatchesV3` — `test_feature_schema_matches_v3`, `test_feature_count_reasonable`, `test_no_all_nan_features`
  2. `TestTrainTestNoOverlap` — `test_train_test_no_overlap`, `test_embargo_gap_exists`, `test_cpcv_no_overlap`
  3. `TestModelSaveLoadRoundtrip` — `test_model_save_load_roundtrip`, `test_model_registry_roundtrip`
  4. `TestPredictSingleSampleLatency` — `test_predict_single_sample_latency` (<50ms P95)
  5. `TestEarlyStoppingReducesEstimators` — `test_early_stopping_reduces_estimators`
  6. `TestOverfitTriggersWarning` — `test_overfit_triggers_warning`, `test_overfit_warning_with_degenerate_model`
  7. `TestMultipleTestingCorrection` — `test_benjamini_hochberg_basic`, `test_bh_empty_input`, `test_bh_adjusted_monotone`

## Bugs Fixed

### 1. test_cpcv_no_overlap — ModuleNotFoundError
- **Root cause**: Package installed as `graxia.packages.quant_os`; `core.cross_validation` not importable as standalone top-level module in pytest context
- **Fix**: Added fallback import `from graxia.packages.quant_os.core.cross_validation import combine_purged_k_fold_cv`

### 2. test_early_stopping_reduces_estimators — XGBoost eval_metric mismatch
- **Root cause**: Test used `eval_metric="logloss"` but labels have 3 classes (0, 1, 2), requiring `mlogloss`
- **Fix**: Auto-detect `n_classes` and select `mlogloss` if > 2, else `logloss`

## Test Results

```
15 passed in 16.02s
```

All tests pass including:
- Feature schema validation
- Train/test overlap detection with CPCV
- Model save/load roundtrip integrity
- Single-sample prediction latency (<50ms P95)
- Early stopping effectiveness
- Overfit detection
- Benjamini-Hochberg multiple testing correction

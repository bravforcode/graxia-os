# DETERMINISM AUDIT — Phase 19

## Executive Summary

ML model training uses hardcoded seeds (`random_state=42`) for reproducibility, but **numpy's global state is not seeded**, and some test fixtures use global `random.seed()` which could leak between tests.

## Critical Findings

### CRIT-19-01: Missing numpy Random Seed
**Severity**: HIGH
**File**: `ml/pipeline.py`
**Impact**: Feature engineering uses pandas_ta which internally uses numpy. Without `np.random.seed()`, feature values may vary across runs, making model comparisons invalid.

### CRIT-19-02: Global random.seed() in Fixtures
**Severity**: MEDIUM
**File**: `backtest/xauusd_liquidity_sweep_fixture.py:18`
```python
random.seed(2025_06_22)
```
**Impact**: Global state mutation could affect other tests if they run in the same process. Should use `random.Random(seed)` instead.

### CRIT-19-03: XGBoost Determinism Caveat
**Severity**: LOW
**File**: `ml/pipeline.py:420`
**Impact**: `tree_method="hist"` is deterministic on the same hardware but may produce different results on different CPU architectures or with different numbers of threads.

## Seed Inventory

| Module | Seed | Scope | Status |
|--------|------|-------|--------|
| `ml/pipeline.py` | `random_state=42` | XGBoost/LightGBM/RF | ✅ Proper |
| `ml/ensemble.py` | `random_state=42` | Ensemble models | ✅ Proper |
| `ml/model_registry.py` | `random_seed=42` | Metadata | ✅ Proper |
| `backtest/data_loader.py` | `seed=42` | Sample data | ✅ Local RNG |
| `backtest/metrics.py` | `seed=None` | Bootstrap | ✅ Optional |
| `backtest/xauusd_liquidity_sweep_fixture.py` | `seed=2025_06_22` | Global | ❌ Leaks |

## Positive Findings

1. **ML models**: All use `random_state=42` for training reproducibility
2. **Backtest metrics**: Bootstrap resampling uses local `random.Random(seed)`
3. **Data loader**: Sample data generation uses local RNG
4. **Model registry**: Seed is tracked in metadata for audit trail

## Recommendations

1. **P1**: Add `np.random.seed(42)` in MLTrainer.__init__
2. **P2**: Replace global `random.seed()` with local `random.Random()` in fixtures
3. **P3**: Document determinism caveats for multi-platform deployment
4. **P3**: Consider `PYTHONHASHSEED=0` for full reproducibility

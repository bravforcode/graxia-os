# ML MODEL LIFECYCLE AUDIT — Phase 16

## Executive Summary

The ML lifecycle infrastructure (DriftMonitor, ModelRegistry, AutoRetrain) is **architecturally sound** but has a **CRITICAL gap**: the `evaluate_model()` function in `auto_retrain.py` returns **dummy metrics** instead of real evaluation results, meaning the champion/challenger comparison is non-functional.

## Component Inventory

| Component | File | Status |
|-----------|------|--------|
| DriftMonitor | `ml/drift_monitor.py` | ✅ Production-ready |
| ModelRegistry | `ml/model_registry.py` | ✅ Production-ready |
| MLTrainer | `ml/pipeline.py` | ⚠️ Missing numpy seed |
| AutoRetrain | `scripts/auto_retrain.py` | ❌ Dummy metrics |
| DriftDetector | `ml/pipeline.py` | ✅ Functional |

## Critical Findings

### CRIT-16-01: Dummy Evaluation Metrics in AutoRetrain
**Severity**: CRITICAL
**File**: `scripts/auto_retrain.py:103-110`
```python
def evaluate_model(model_data: dict):
    """Evaluate a model and return metrics object."""
    @dataclass
    class ModelMetrics:
        deflated_sharpe: float = 1.0
        oos_max_drawdown: float = 10.0
    return ModelMetrics()
```
**Impact**: The `hot_swap()` function compares challenger to champion using these dummy values. Since both champion and challenger get the same default metrics, the swap condition `challenger_metrics.deflated_sharpe <= champion_metrics.deflated_sharpe * 1.05` is always satisfied, meaning **every retrained model replaces the champion regardless of quality**.

### CRIT-16-02: Missing numpy Random Seed
**Severity**: HIGH
**File**: `ml/pipeline.py:401-448`
**Impact**: XGBoost, LightGBM, and RandomForest all use `random_state=42`, but numpy's global state is not seeded. This means feature engineering (which uses numpy internally via pandas_ta) produces non-reproducible results across runs.

### CRIT-16-03: DriftMonitor Silent Persistence Failure
**Severity**: MEDIUM
**File**: `ml/drift_monitor.py:300-320`
**Impact**: DuckDB persistence failures are caught and logged but the monitor continues operating in memory-only mode. This could lead to drift history loss on restart without any operator alert.

## Positive Findings

1. **ModelRegistry**: Immutable metadata, JSON sidecars, and index persistence are well-designed
2. **DriftMonitor**: PSI computation, accuracy tracking, and staleness detection are production-quality
3. **Walk-forward training**: Proper OOS evaluation in MLTrainer
4. **Version IDs**: Deterministic naming with timestamp + UUID prevents collisions

## Recommendations

1. **P0**: Implement real `evaluate_model()` with walk-forward OOS metrics
2. **P1**: Add `np.random.seed(42)` at MLTrainer initialization
3. **P2**: Add Prometheus metrics for drift monitor state
4. **P3**: Implement automated promotion gates (not just manual hot_swap)

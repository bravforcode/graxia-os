# RESEARCH METHODOLOGY AUDIT — Phase 17

## Executive Summary

The experiment registry and locked-inputs infrastructure exists but is **not enforced at runtime**. Experiments can be run without registration, and there is no automatic verification that locked parameters match actual execution parameters.

## Component Inventory

| Component | File | Status |
|-----------|------|--------|
| ExperimentRegistry | `validation/experiment_registry.py` | ✅ Well-designed |
| ExperimentRecord | `validation/experiment_registry.py` | ✅ Immutable frozen dataclass |
| LockedInputs | `validation/locked_inputs.py` | ⚠️ Exists but not enforced |
| SearchBudget | `validation/search_budget.py` | ✅ Functional |

## Critical Findings

### CRIT-17-01: Experiment Registry Not Enforced
**Severity**: HIGH
**File**: `validation/experiment_registry.py`
**Impact**: The `ExperimentRegistry.register()` method exists but is never called before experiment execution. Any script can run experiments without registration, bypassing the audit trail.

### CRIT-17-02: No Runtime Parameter Verification
**Severity**: HIGH
**File**: `validation/locked_inputs.py`
**Impact**: Locked inputs are stored but never compared against actual execution parameters. A researcher could change strategy parameters without detection.

### CRIT-17-03: Budget Check is Advisory Only
**Severity**: MEDIUM
**File**: `validation/experiment_registry.py:80-83`
```python
def check_budget(self, strategy_hash: str, budget: int = 12) -> bool:
    count = sum(1 for e in self._experiments.values() if e.strategy_snapshot_hash == strategy_hash)
    return count < budget
```
**Impact**: The budget check returns a boolean but doesn't prevent execution. Experiments can exceed the search budget without error.

## Positive Findings

1. **Fingerprinting**: `ExperimentRecord.fingerprint()` provides SHA-256 verification of experiment identity
2. **Immutability**: Frozen dataclass prevents post-hoc modification of records
3. **Persistence**: JSON registry persists across runs
4. **Budget tracking**: Per-strategy experiment counts are maintained

## Recommendations

1. **P1**: Add pre-execution hook that requires experiment registration
2. **P1**: Implement parameter comparison between locked and actual values
3. **P2**: Make budget check enforceable (raise on exceeded budget)
4. **P3**: Add experiment comparison and reporting tools

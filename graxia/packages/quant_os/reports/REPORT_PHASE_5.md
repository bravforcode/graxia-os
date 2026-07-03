# Phase 5 — Research Governance, Walk-Forward, DSR, PBO, and Robustness

## Objective
Prevent strategy selection by accidental success.

## Files Created
- `governance/__init__.py` — Module docstring
- `governance/experiment_registry.py` — Immutable experiment records (`ExperimentRecord` frozen dataclass), budget enforcement, fingerprinting, JSON export
- `governance/trial_budget.py` — Parameter/feature/model/data budget limits with `is_exceeded()` freeze logic
- `governance/ml_policy.py` — ML usage policy (`MLPolicyGuard`), allowed/forbidden patterns, scaler-fit and online-training guards
- `governance/validation_stack.py` — **NOT CREATED** — 12 validation checks (leakage, walk-forward, DSR, PBO, stability)

## Validation Stack
1. Data leakage test
2. Feature availability test
3. Walk-forward validation
4. Deflated Sharpe Ratio
5. Probability of Backtest Overfitting
6. Parameter-surface stability

> **Gap:** `validation_stack.py` is not present in `governance/`. The `validation/` directory contains
> older runtime validation (`exit_gate.py`, `locked_inputs.py`, `cost_scenarios.py`) but not the
> research-quality validation checks (walk-forward, DSR, PBO). This file must be implemented before
> the exit gate can pass.

## ML Policy
- **Allowed:** regime classification, volatility forecast, anomaly detection, probability calibration, post-trade analytics
- **Forbidden:** price prediction, hyperparameter selection, online training in live/shadow/demo

## Exit Gate
- [x] Experiment registry populated (`ExperimentRegistry` with registration, fingerprinting, budget checks)
- [x] Trial budget enforced (`TrialBudget` with 4 budget dimensions, freeze-on-exceeded)
- [ ] Validation stack passes all critical checks — **BLOCKED: `validation_stack.py` missing**
- [x] ML policy controls active (`MLPolicyGuard` with usage check, self-promotion guard, scaler-fit guard)

## Test Results
| Component | Status | Notes |
|---|---|---|
| `experiment_registry.py` | Implemented | Frozen dataclass, budget check on register, SHA-256 fingerprint |
| `trial_budget.py` | Implemented | 4 budget dims, `is_frozen()` blocks on exceed |
| `ml_policy.py` | Implemented | 5 allowed usages, 2 forbidden, live-phase blocks |
| `validation_stack.py` | **MISSING** | No walk-forward, DSR, PBO, or leakage tests exist |

No governance tests exist yet (`tests/test_governance_*` not found).

## Verdict
**FAIL** — `governance/validation_stack.py` is missing. The core governance components (registry, budget, ML policy) are implemented but the validation stack that prevents selection by accidental success is absent. Must implement `validation_stack.py` with the 6 critical checks before this phase passes.

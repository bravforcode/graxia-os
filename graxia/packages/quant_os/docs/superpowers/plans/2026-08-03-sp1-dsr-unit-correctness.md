# SP1: DSR Unit Correctness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all DSR call sites to pass correctly-unit'd (per-observation) Sharpe ratios, add a `dsr_from_annualized` helper that prevents future unit mistakes, re-run trials 1028/3008/1032 verdicts, and update tests.

**Architecture:** Add one helper `dsr_from_annualized()` in `validation/deflated_sharpe.py` that takes an annualized Sharpe + `annualization_factor` and de-annualizes internally via `factor=√annualization_factor`. Migrate 15 production call sites + 2 wrong defaults to the helper. Fix n_observations swaps, kurtosis convention, duplicate impl in tsm_validate. Then re-run the 3 trial harnesses, update ledger/artifacts, fix tests.

**Tech Stack:** Python 3.12, pandas, numpy, math, pytest, pre-commit (ruff + trailing-whitespace + eof hooks).

**Spec:** `docs/superpowers/specs/2026-08-03-sp1-dsr-unit-correctness-design.md` (approved 2026-08-03)
**Research:** `reports/deep_research_institutional_gates_20260803.md` §7 (exhaustive audit)

## Global Constraints

- Do NOT modify the formula inside `deflated_sharpe_ratio()` — it is correct; only caller units were wrong.
- `deflated_sharpe_ratio` signature must remain backward-compatible (callers pass `sharpe_annualization_factor` through variables — `core/param_sweep.py:108`, `validation/search_budget.py:116`).
- All trials keep frozen parameters from pre-registration; only DSR call changes.
- Commit per logical task with Conventional Commits: `fix(quant_os): ...`
- Run pre-commit hooks (they run automatically on commit; fix trailing whitespace if rejected).
- Tests must pass: `pytest tests/test_dsr_from_annualized.py tests/test_min_btl.py tests/test_phase_5_statistical.py tests/test_phase_5_integration.py tests/test_overfitting_pipeline.py tests/test_ws_a_tsmom.py -q`
- Workdir: `graxia/packages/quant_os` (repo root: `C:/Users/menum/graxia os`)

---

### Task 1: Add `dsr_from_annualized` helper + guard (TDD)

**Files:**
- Modify: `validation/deflated_sharpe.py` (append after `deflated_sharpe_ratio`, before `MinBTLResult` dataclass)
- Create: `tests/test_dsr_from_annualized.py`

**Interfaces:**
- Produces: `dsr_from_annualized(observed_sharpe: float, n_trials: int, n_observations: int, *, annualization_factor: float = 252.0, skewness: float = 0.0, kurtosis: float = 3.0, confidence_level: float = 0.95) -> DeflatedSharpeResult`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dsr_from_annualized.py
"""Regression tests for dsr_from_annualized (SP1: DSR unit correctness)."""

import importlib.util
import math
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("deflated_sharpe", str(_ROOT / "validation" / "deflated_sharpe.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
dsr_from_annualized = _mod.dsr_from_annualized
deflated_sharpe_ratio = _mod.deflated_sharpe_ratio


def test_trial_1032_scenario_fails_with_correct_factor():
    """SR=0.34 annualized, N=1050, N_obs=5392, daily bars -> must FAIL (p~0.955).
    This is the exact trial 1032 numbers that falsely PASSed with factor=1.0."""
    r = dsr_from_annualized(0.34, 1050, 5392, annualization_factor=252)
    assert not r.passes_threshold
    assert r.probability_alpha > 0.90  # ~0.955


def test_high_sharpe_passes():
    """SR=2.0 annualized must PASS at N=1050."""
    r = dsr_from_annualized(2.0, 1050, 5392, annualization_factor=252)
    assert r.passes_threshold


def test_annualization_factor_affects_result():
    """H1 (6096 bars/yr) must differ from D1 (252) — proves factor is not hardcoded."""
    r_d1 = dsr_from_annualized(1.0, 1050, 5392, annualization_factor=252)
    r_h1 = dsr_from_annualized(1.0, 1050, 5392, annualization_factor=6096)
    # H1 de-annualizes less (SR/sqrt(6096) smaller) -> less significant
    assert r_h1.probability_alpha > r_d1.probability_alpha


def test_kurtosis_raw_convention():
    """Helper must treat kurtosis as RAW (3=normal). Excess kurtosis (0) must differ."""
    r_raw = dsr_from_annualized(3.0, 50, 5000, annualization_factor=252, kurtosis=3.0)
    r_excess = dsr_from_annualized(3.0, 50, 5000, annualization_factor=252, kurtosis=0.0)
    assert r_raw.probability_alpha != r_excess.probability_alpha


def test_single_trial_not_overpenalized():
    """n_trials=1 (no multiple testing) must not crash and must be less conservative."""
    r = dsr_from_annualized(1.5, 1, 5000, annualization_factor=252)
    assert r.passes_threshold  # no multiplicity penalty with N=1


def test_equivalence_with_direct_call():
    """dsr_from_annualized(f) == deflated_sharpe_ratio(factor=sqrt(f))."""
    r1 = dsr_from_annualized(1.2, 100, 3000, annualization_factor=252,
                             skewness=0.1, kurtosis=3.5)
    r2 = deflated_sharpe_ratio(1.2, 100, 3000, sharpe_annualization_factor=math.sqrt(252),
                               skewness=0.1, kurtosis=3.5)
    assert r1.probability_alpha == r2.probability_alpha
    assert r1.passes_threshold == r2.passes_threshold
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dsr_from_annualized.py -q`
Expected: FAIL with `AttributeError: module has no attribute 'dsr_from_annualized'`

- [ ] **Step 3: Write minimal implementation**

Append to `validation/deflated_sharpe.py` (after `deflated_sharpe_ratio` function ends at line ~117, before `MinBTLResult` at line ~120):

```python
def dsr_from_annualized(
    observed_sharpe: float,
    n_trials: int,
    n_observations: int,
    *,
    annualization_factor: float = 252.0,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    confidence_level: float = 0.95,
) -> DeflatedSharpeResult:
    """DSR for an ANNUALIZED Sharpe ratio.

    Bailey & Lopez de Prado (2014) Eq.(2) requires a per-observation Sharpe:
    the Lo (2002) sr_std formula breaks when an annualized SR is passed with
    raw-bar n_observations (z is inflated ~sqrt(periods_per_year)x, producing
    false PASS verdicts — see reports/deep_research_institutional_gates_20260803.md §7).
    This helper de-annualizes internally so callers cannot get the units wrong.

    Args:
        observed_sharpe: Annualized Sharpe ratio from backtest.
        n_trials: Number of strategy trials (multiple testing correction).
        n_observations: Raw per-period observation count (e.g. daily bars)
            backing observed_sharpe.
        annualization_factor: Bars/periods per year used to annualize
            (252=D1, 6096=H1, 96, 24, etc. — must match caller's scaling).
        skewness: RAW return skewness (0 for normal).
        kurtosis: RAW return kurtosis (3 for normal — NOT excess).
        confidence_level: Confidence for the pass threshold.

    Returns:
        DeflatedSharpeResult computed with correct per-observation units.
    """
    if annualization_factor <= 1:
        import warnings

        warnings.warn(
            f"dsr_from_annualized: annualization_factor={annualization_factor} <= 1 "
            "looks like a unit error (expected bars/year like 252, 6096).",
            stacklevel=2,
        )
        annualization_factor = 252.0

    return deflated_sharpe_ratio(
        observed_sharpe=observed_sharpe,
        n_trials=n_trials,
        n_observations=n_observations,
        sharpe_annualization_factor=math.sqrt(annualization_factor),
        skewness=skewness,
        kurtosis=kurtosis,
        confidence_level=confidence_level,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dsr_from_annualized.py -q`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add validation/deflated_sharpe.py tests/test_dsr_from_annualized.py
git commit -m "feat(quant_os): dsr_from_annualized helper — unit-safe DSR entry point"
```

---

### Task 2: Migrate trial harnesses 1028/3008/1032 to the helper

**Files:**
- Modify: `scripts/run_ws_a_tsmom.py:484-491`
- Modify: `scripts/run_fx_carry_3008.py:418-425`
- Modify: `scripts/run_52week_high_1032.py:399-410`

**Interfaces:**
- Consumes: `dsr_from_annualized` (Task 1)

- [ ] **Step 1: Fix `run_ws_a_tsmom.py` (trial 1028)**

Replace the DSR block (currently lines 484-491):

```python
        # Compute DSR
        _port_df = result["portfolio_returns"]
        dsr_result = _ds_mod.deflated_sharpe_ratio(
            observed_sharpe=m["sharpe"],
            n_trials=n_trials,
            n_observations=len(_port_df),
            sharpe_annualization_factor=1.0,  # TODO(DSR-AUDIT): unaudited call site, factor=1.0 preserves prior (possibly-incorrect) behavior — see MATH_CORRECTNESS_AUDIT.md
            skewness=float(_port_df["return"].skew()),
            kurtosis=float(_port_df["return"].kurtosis()),
        )
```

with:

```python
        # Compute DSR — annualized Sharpe, daily bars: factor=sqrt(252) via helper
        _port_df = result["portfolio_returns"]
        dsr_result = _ds_mod.dsr_from_annualized(
            observed_sharpe=m["sharpe"],
            n_trials=n_trials,
            n_observations=len(_port_df),
            annualization_factor=252,
            skewness=float(_port_df["return"].skew()),
            kurtosis=float(_port_df["return"].kurtosis()) + 3.0,  # pandas kurtosis() is EXCESS; module expects RAW
        )
```

- [ ] **Step 2: Fix `run_fx_carry_3008.py`**

Find the same pattern at lines ~418-425 (uses `_ds_mod.deflated_sharpe_ratio` with `sharpe_annualization_factor=1.0` and `_port_df["return"].kurtosis()`). Replace with the same `dsr_from_annualized(... annualization_factor=252, kurtosis=float(_port_df["return"].kurtosis()) + 3.0)` pattern.

- [ ] **Step 3: Fix `run_52week_high_1032.py`**

Find the same pattern at lines ~399-410. Replace with the same `dsr_from_annualized(...)` pattern (annualization_factor=252, kurtosis +3.0).

- [ ] **Step 4: Verify all 3 harnesses still run**

Run:
```bash
python scripts/run_52week_high_1032.py 2>&1 | Select-Object -Last 12
python scripts/run_fx_carry_3008.py 2>&1 | Select-Object -Last 12
```
Expected: DSR line now shows `probability alpha ~0.955` (FAIL) for 1032 and similar for 3008 (both were previously `0.000000 PASS`). 1028's DSR now FAILs too.
**IMPORTANT:** This is the expected verdict flip — record the NEW numbers.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_ws_a_tsmom.py scripts/run_fx_carry_3008.py scripts/run_52week_high_1032.py
git commit -m "fix(quant_os): trial harnesses use dsr_from_annualized — DSR now unit-correct"
```

---

### Task 3: Migrate pipeline scripts (institutional_pipeline, run_complete_analysis, run_multi_symbol_wf)

**Files:**
- Modify: `scripts/institutional_pipeline.py:125-132`
- Modify: `scripts/run_complete_analysis.py:177-179`
- Modify: `scripts/run_multi_symbol_wf.py:203-208`

**Interfaces:**
- Consumes: `dsr_from_annualized` (Task 1)

- [ ] **Step 1: Fix `institutional_pipeline.py`**

At line ~125, replace the direct `deflated_sharpe_ratio(...)` call (which computes skew/kurt inline from returns and passes factor=1.0) with:

```python
        dsr = deflated_sharpe_ratio(
            observed_sharpe=sharpe,
            n_trials=n_total_trials,
            n_observations=n_obs,
            sharpe_annualization_factor=1.0,  # TODO(DSR-AUDIT): unaudited call site, factor=1.0 preserves prior (possibly-incorrect) behavior — see MATH_CORRECTNESS_AUDIT.md
            skewness=skew,
            kurtosis=kurt,
        )
```

→

```python
        dsr = dsr_from_annualized(
            observed_sharpe=sharpe,
            n_trials=n_total_trials,
            n_observations=n_obs,
            annualization_factor=252,
            skewness=skew,
            kurtosis=kurt,
        )
```

Also update the import at the top of the file: the module is loaded via `_dsr_mod = _load_module("deflated_sharpe", ...)`; add `dsr_from_annualized = _dsr_mod.dsr_from_annualized` after line 69.

- [ ] **Step 2: Fix `run_complete_analysis.py`**

At line ~177, replace:

```python
            ds = ds_mod.deflated_sharpe_ratio(
                avg_sharpe, N_FOLDS * len(CONF_THRESHOLDS), total_trades, sharpe_annualization_factor=1.0
            )
```

with:

```python
            ds = ds_mod.dsr_from_annualized(
                avg_sharpe, N_FOLDS * len(CONF_THRESHOLDS), total_trades, annualization_factor=252
            )
```

Note: `total_trades` remains as n_observations here ONLY if the Sharpe was computed per-trade (trade-level). Check the context: if `avg_sharpe` was annualized from per-trade returns, `total_trades` is the correct n. If from bar returns, it should be bars. Leave as-is unless a comment in the file says bar-based — record in the commit message which was chosen.

- [ ] **Step 3: Fix `run_multi_symbol_wf.py`**

At line ~203, replace:

```python
        ds_result = ds_mod.deflated_sharpe_ratio(
            observed_sharpe=avg_sharpe,
            n_trials=N_FOLDS * len(conf_thresholds),
            n_observations=total_trades,
            sharpe_annualization_factor=1.0,  # TODO(DSR-AUDIT): unaudited call site, factor=1.0 preserves prior (possibly-incorrect) behavior — see MATH_CORRECTNESS_AUDIT.md
        )
```

with:

```python
        ds_result = ds_mod.dsr_from_annualized(
            observed_sharpe=avg_sharpe,
            n_trials=N_FOLDS * len(conf_thresholds),
            n_observations=total_trades,
            annualization_factor=252,
        )
```

(Same trade-level n_observations note as Task 3 Step 2.)

- [ ] **Step 4: Verify no syntax errors**

Run: `python -m py_compile scripts/institutional_pipeline.py scripts/run_complete_analysis.py scripts/run_multi_symbol_wf.py`
Expected: exit 0, no output

- [ ] **Step 5: Commit**

```bash
git add scripts/institutional_pipeline.py scripts/run_complete_analysis.py scripts/run_multi_symbol_wf.py
git commit -m "fix(quant_os): pipeline scripts use dsr_from_annualized (unit-correct DSR)"
```

---

### Task 4: Migrate H1/WF/ML scripts (run_xauusd_h1_wf, train_mega_model, run_deflated_sharpe, effective_n, _check_dsr, pre_freeze_checks, run_ws_a)

**Files:**
- Modify: `scripts/run_xauusd_h1_wf.py:133-135`
- Modify: `scripts/train_mega_model.py:567-572`
- Modify: `scripts/run_deflated_sharpe.py:87-94`
- Modify: `scripts/effective_n_and_outlier_deep.py:303-310`
- Modify: `_check_dsr.py:49-55`
- Modify: `scripts/pre_freeze_checks.py:74-91`
- Modify: `scripts/run_ws_a.py:332-339`

**Interfaces:**
- Consumes: `dsr_from_annualized` (Task 1)

- [ ] **Step 1: Fix `run_xauusd_h1_wf.py` (H1 = 6096 bars/yr)**

At line ~133, replace:

```python
    ds = ds_mod.deflated_sharpe_ratio(
        avg_sharpe, N_FOLDS * len(CONF_THRESHOLDS), total_trades, sharpe_annualization_factor=1.0
    )
```

with:

```python
    ds = ds_mod.dsr_from_annualized(
        avg_sharpe, N_FOLDS * len(CONF_THRESHOLDS), total_trades, annualization_factor=6096
    )
```

- [ ] **Step 2: Fix `train_mega_model.py`**

At line ~567, replace:

```python
        ds_result = deflated_sharpe_ratio(
            observed_sharpe=ens_metrics.get("sharpe_ratio", 0),
            n_trials=N_TRIALS,
            n_observations=len(y_test),
            sharpe_annualization_factor=1.0,  # TODO(DSR-AUDIT): unaudited call site, factor=1.0 preserves prior (possibly-incorrect) behavior — see MATH_CORRECTNESS_AUDIT.md
        )
```

with:

```python
        ds_result = deflated_sharpe_ratio(
            observed_sharpe=ens_metrics.get("sharpe_ratio", 0),
            n_trials=N_TRIALS,
            n_observations=len(y_test),
            sharpe_annualization_factor=math.sqrt(252),
            skewness=0.0,
            kurtosis=3.0,
        )
```

(Or use the helper import — check whether `deflated_sharpe_ratio` is imported at top; if the file imports it via `from validation.deflated_sharpe import deflated_sharpe_ratio`, switch the call to `dsr_from_annualized` instead. Prefer helper.)

- [ ] **Step 3: Fix `run_deflated_sharpe.py` (CLI annualization arg)**

At line ~85-94, the code does `sr_hat = mean_ret / std_ret * (annualization ** 0.5)` then calls with factor=1.0. Replace the DSR call with:

```python
    result = _real_dsr(
        observed_sharpe=sr_hat,
        n_trials=n_trials,
        n_observations=n_obs,
        sharpe_annualization_factor=1.0,  # TODO(DSR-AUDIT): unaudited call site, factor=1.0 preserves prior (possibly-incorrect) behavior — see MATH_CORRECTNESS_AUDIT.md
        skewness=skew,
        kurtosis=kurt,
    )
```

→

```python
    result = _real_dsr(
        observed_sharpe=sr_hat,
        n_trials=n_trials,
        n_observations=n_obs,
        sharpe_annualization_factor=annualization ** 0.5,  # sr_hat was scaled by annualization**0.5 above
        skewness=skew,
        kurtosis=kurt,
    )
```

- [ ] **Step 4: Fix `effective_n_and_outlier_deep.py`**

At line ~303, replace `sharpe_annualization_factor=1.0` with `sharpe_annualization_factor=math.sqrt(252)` (keep the same `deflated_sharpe_ratio` call — this file already passes skew/kurt correctly).

- [ ] **Step 5: Fix `_check_dsr.py` (also fix excess kurtosis)**

At lines 44-55:
- Line 44: `kurt = float(np.mean(z ** 4) - 3)` → `kurt = float(np.mean(z ** 4))` (RAW kurtosis, matches module)
- Remove the clamp line 53 (`kurt_clamped = max(kurt, -2.0)`) and use `kurt` directly
- Lines 49/55: `sharpe_annualization_factor=1.0` → `sharpe_annualization_factor=math.sqrt(252)`

- [ ] **Step 6: Fix `pre_freeze_checks.py`**

At lines 74-91: both DSR calls (actual + default) use `ann_sharpe` (annualized via `* math.sqrt(252)` at line 71) with factor=1.0. Change both `sharpe_annualization_factor=1.0` → `sharpe_annualization_factor=math.sqrt(252)`.

- [ ] **Step 7: Fix `run_ws_a.py` (also fix n_observations swap)**

At lines 330-339:
- Line 331: `pooled_sharpe = ... * math.sqrt(252)` (annualized — keep)
- Line 335: `n_observations=1050` → `n_observations=len(cs_mean)` (1050 was n_trials!)
- Line 336: `sharpe_annualization_factor=1.0` → `sharpe_annualization_factor=math.sqrt(252)`
- Line 338: `kurtosis=float(cs_mean.kurt())` → `kurtosis=float(cs_mean.kurt()) + 3.0` (raw convention)

- [ ] **Step 8: Verify compile + no import breakage**

Run: `python -m py_compile scripts/run_xauusd_h1_wf.py scripts/train_mega_model.py scripts/run_deflated_sharpe.py scripts/effective_n_and_outlier_deep.py _check_dsr.py scripts/pre_freeze_checks.py scripts/run_ws_a.py`
Expected: exit 0

- [ ] **Step 9: Commit**

```bash
git add scripts/run_xauusd_h1_wf.py scripts/train_mega_model.py scripts/run_deflated_sharpe.py scripts/effective_n_and_outlier_deep.py _check_dsr.py scripts/pre_freeze_checks.py scripts/run_ws_a.py
git commit -m "fix(quant_os): remaining DSR call sites unit-correct + n_observations + kurtosis raw"
```

---

### Task 5: Fix wrong defaults (search_budget, param_sweep)

**Files:**
- Modify: `validation/search_budget.py:90`
- Modify: `core/param_sweep.py:98`

- [ ] **Step 1: Fix `search_budget.py` default**

At line 90, change signature default:

```python
        sharpe_annualization_factor: float = 1.0,
```

→

```python
        sharpe_annualization_factor: float = 1.0,  # SP1-AUDIT: keep 1.0 default? see note
```

Wait — these defaults are used when callers pass RAW per-observation Sharpe (n_observations matches). DO NOT blindly change to √252. Instead, add a guard comment and verify actual callers:

- [ ] **Step 2: Verify actual callers of `get_deflated_sharpe`**

Run: `python -m pytest tests/test_phase_5_integration.py -q` and grep for `get_deflated_sharpe` callers.

Check: if callers pass annualized SR with bar n_observations, change the DEFAULT to 252 and add docstring note: "default 252 assumes annualized Sharpe; pass 1.0 for raw per-observation". If callers already pass explicit factor, leave default but add the docstring.

**Decision rule (from spec §Component B row 14/15):** change the default to `annualization_factor`-style semantics ONLY where the surrounding class documentation states the Sharpe is annualized. Verify with the actual caller code before changing.

- [ ] **Step 3: Apply chosen fix to both files**

For `search_budget.py` and `param_sweep.py`, apply the same change: update the docstring to require explicit factor and add:

```python
        if sharpe_annualization_factor <= 1.0:
            warnings.warn(
                "sharpe_annualization_factor<=1.0 with an annualized Sharpe is a unit error; "
                "pass sqrt(bars_per_year) or use dsr_from_annualized().",
                stacklevel=2,
            )
```

- [ ] **Step 4: Commit**

```bash
git add validation/search_budget.py core/param_sweep.py
git commit -m "fix(quant_os): DSR factor default guard in search_budget + param_sweep"
```

---

### Task 6: Fix artifact 1028 (n_observations swap)

**Files:**
- Modify: `reports/ws_a_trial_1028.json`

- [ ] **Step 1: Fix n_observations + add honest note**

Edit the `dsr` block:

```json
"dsr": {
  "pooled_sharpe": 0.1519,
  "probability_alpha": 0.0,
  "n_observations": 1050,
  "pass": true
}
```

→

```json
"dsr": {
  "pooled_sharpe": 0.1519,
  "probability_alpha": 0.0,
  "n_observations": 5621,
  "pass": true,
  "honest_note": "SP1 audit 2026-08-03: n_observations was swapped with n_trials (1050). Corrected to total_days=5621. DSR itself still computed with factor=1.0 in the original run — verdict was REJECTED on DK gate regardless; DSR pass is unreliable."
}
```

- [ ] **Step 2: Validate JSON**

Run: `python -c "import json; json.load(open('reports/ws_a_trial_1028.json', encoding='utf-8')); print('valid')"`
Expected: valid

- [ ] **Step 3: Commit**

```bash
git add reports/ws_a_trial_1028.json
git commit -m "fix(quant_os): correct n_observations swap in trial 1028 artifact"
```

---

### Task 7: Fix duplicate DSR impl in tsm_validate.py

**Files:**
- Modify: `scripts/tsm_validate.py:396-442`

- [ ] **Step 1: Replace duplicate implementation with delegation**

Replace the entire `def deflated_sharpe_ratio(...)` function (lines 396-442) with a thin wrapper that imports the shared module:

```python
def deflated_sharpe_ratio(sharpe: float, n_obs: int, n_trials: int, skew: float = 0.0, kurtosis: float = 3.0) -> dict:
    """DSR via shared validation module (SP1: removed duplicate impl).

    NOTE: `sharpe` here must be the ANNUALIZED Sharpe (historical callers pass
    full_metrics['sharpe'] which is annualized); n_obs is bars. De-annualize
    with 252 daily bars. Returns dict shape compatible with old callers.
    """
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("dsr", str(Path(__file__).resolve().parent.parent / "validation" / "deflated_sharpe.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    result = mod.dsr_from_annualized(
        observed_sharpe=sharpe,
        n_trials=n_trials,
        n_observations=n_obs,
        annualization_factor=252,
        skewness=skew,
        kurtosis=kurt,
    )
    return {
        "sharpe": sharpe,
        "deflated_sharpe": result.deflated_sharpe,
        "z_score": 0.0,  # legacy field — not computed by shared module
        "se": 0.0,
        "p_value_single": 0.0,
        "p_value_deflated": 1.0 - result.probability_alpha,
        "e_max_z": 0.0,
        "n_trials": n_trials,
        "significant_5pct": result.passes_threshold,
    }
```

- [ ] **Step 2: Verify callers still work**

Run: `python -m py_compile scripts/tsm_validate.py`
Then check the two internal callers (lines 517, 573) still produce dict with the keys they read. Read lines 510-580 to confirm keys used (`dsr["p_value_deflated"]`, `dsr["significant_5pct"]`, etc.) — if different keys are read, map them in the wrapper return dict.

- [ ] **Step 3: Commit**

```bash
git add scripts/tsm_validate.py
git commit -m "fix(quant_os): tsm_validate DSR delegates to shared module — remove divergent duplicate impl"
```

---

### Task 8: Re-run trials + update ledger/registry (append-only)

**Files:**
- Modify: `research/trial_ledger.json` (trial 1032 note)
- Modify: `research/trial_ledger_b.json` (trial 3008 note)
- Modify: `research/hypothesis_registry.json` (trial 1032 entry)

- [ ] **Step 1: Re-run all 3 trials and capture NEW DSR numbers**

Run:
```bash
python scripts/run_52week_high_1032.py 2>&1 | Select-String -Pattern "DSR|Probability|passes|GATE|verdict|Sharpe"
python scripts/run_fx_carry_3008.py 2>&1 | Select-String -Pattern "DSR|Probability|passes|GATE|verdict|Sharpe"
python scripts/run_ws_a_tsmom.py 2>&1 | Select-String -Pattern "DSR|Probability|passes|GATE|verdict|Sharpe"
```
Record the new `probability_alpha` values (expected: all FAIL now, p≈0.955 for 1032).

- [ ] **Step 2: Update trial_ledger.json entry for 1032**

Add to the 1032 entry's note (append, don't rewrite history):

```json
      "note": "... SP1 audit 2026-08-03: DSR re-run with unit-correct factor (sqrt(252)); probability_alpha flipped from 0.0 (artifact) to 0.955. Verdict unchanged (REJECTED on DK t=0.461 << 2.0).",
```

- [ ] **Step 3: Update trial_ledger_b.json entry for 3008**

Append similar note about DSR p flipping (3008 was p=1.0 already FAIL — confirm the new value matches).

- [ ] **Step 4: Update hypothesis_registry.json 1032 entry**

Append to `result_summary.conclusion` or add `"dsr_correction_note"` field documenting the flip.

- [ ] **Step 5: Validate all JSON**

Run: `python -c "import json; [json.load(open(f, encoding='utf-8')) for f in ['research/trial_ledger.json','research/trial_ledger_b.json','research/hypothesis_registry.json']]; print('valid')"`
Expected: valid

- [ ] **Step 6: Commit**

```bash
git add research/trial_ledger.json research/trial_ledger_b.json research/hypothesis_registry.json reports/trial_1032_52week_high_results.json reports/trial_3008_fx_carry_results.json
git commit -m "docs(quant_os): record DSR unit-correction verdict flips for trials 1028/3008/1032"
```

---

### Task 9: Fix existing tests (25+ call sites)

**Files:**
- Modify: `tests/test_min_btl.py`
- Modify: `tests/test_overfitting_pipeline.py`
- Modify: `tests/test_phase_5_statistical.py`
- Modify: `tests/test_phase_5_integration.py`
- Modify: `tests/test_ws_a_tsmom.py` (if it calls DSR)

**Interfaces:**
- Consumes: `dsr_from_annualized` (Task 1)

- [ ] **Step 1: Audit test semantics — which use raw vs annualized Sharpe**

For each `deflated_sharpe_ratio(...)` / `min_backtest_length(...)` call in tests, determine:
- If the test asserts on an **annualized** Sharpe (SR≥1 with daily-bar n_observations) → the intent is annualized → **switch to `dsr_from_annualized`** and update expected values (they will change because the result is now correct).
- If the test deliberately models **raw per-observation** Sharpe (SR<1 or explicit comment) → keep `sharpe_annualization_factor=1.0`.

- [ ] **Step 2: Update `test_min_btl.py`**

The tests pass `observed_sharpe=2.0..5.0` with `n_observations=5000` and `sharpe_annualization_factor=1.0` — these model **raw** per-period Sharpe (the MinBTL math uses raw). Check each: if `current_observations` is bars (e.g. 5000), and observed_sharpe is ≥1, that's inconsistent with raw per-day SR (impossible for real daily data) → these are ANNUALIZED → switch to `dsr_from_annualized`-style via the module's `min_backtest_length` with `sharpe_annualization_factor=math.sqrt(252)`.

After change, re-run and update the expected `min_observations` values to whatever the corrected function returns (the test's intent is the math correctness, not specific values).

- [ ] **Step 3: Update `test_phase_5_statistical.py` / `test_phase_5_integration.py`**

Same audit: SR=3.0/1.5 with n_obs=500/1000 — annualized → factor=√252. Update expected pass/fail assertions accordingly (e.g. SR=3.0 annualized with N=10 → still PASS; SR=1.5 with N=500 → FAIL now instead of PASS).

- [ ] **Step 4: Update `test_overfitting_pipeline.py`**

Lines 237-240 use factor=1.0 with SR=2.0/3.0 → annualized → factor=√252. Lines 34-41 (MinBTL) → same as test_min_btl. Line 158 already uses √252 (correct).

- [ ] **Step 5: Run the full test batch**

Run:
```bash
python -m pytest tests/test_dsr_from_annualized.py tests/test_min_btl.py tests/test_phase_5_statistical.py tests/test_phase_5_integration.py tests/test_overfitting_pipeline.py tests/test_ws_a_tsmom.py -q
```
Expected: all PASS. If any assertion fails on specific numeric values, update the assertion to the corrected value (document why in the commit).

- [ ] **Step 6: Commit**

```bash
git add tests/test_min_btl.py tests/test_overfitting_pipeline.py tests/test_phase_5_statistical.py tests/test_phase_5_integration.py tests/test_ws_a_tsmom.py
git commit -m "test(quant_os): update DSR/MinBTL tests to unit-correct annualization factors"
```

---

### Task 10: Final verification

- [ ] **Step 1: Run full targeted regression**

Run: `python -m pytest tests/test_dsr_from_annualized.py tests/test_min_btl.py tests/test_phase_5_statistical.py tests/test_phase_5_integration.py tests/test_overfitting_pipeline.py tests/test_ws_a_tsmom.py -q`
Expected: all PASS

- [ ] **Step 2: Compile all touched production files**

Run: `python -m py_compile validation/deflated_sharpe.py scripts/run_ws_a_tsmom.py scripts/run_fx_carry_3008.py scripts/run_52week_high_1032.py scripts/institutional_pipeline.py scripts/run_complete_analysis.py scripts/run_multi_symbol_wf.py scripts/run_xauusd_h1_wf.py scripts/train_mega_model.py scripts/run_deflated_sharpe.py scripts/effective_n_and_outlier_deep.py _check_dsr.py scripts/pre_freeze_checks.py scripts/run_ws_a.py scripts/tsm_validate.py validation/search_budget.py core/param_sweep.py`
Expected: exit 0

- [ ] **Step 3: Verify no remaining factor=1.0 DSR sites (production only)**

Run:
```bash
python -X utf8 -c "import re; from pathlib import Path; [print(p, ':', txt[:txt.find('sharpe_annualization_factor')].count(chr(10))+1) for p in Path('.').rglob('*.py') if '.freebuff' not in p.parts and 'test' not in p.parts and (txt := p.read_text(encoding='utf-8', errors='ignore')).count('sharpe_annualization_factor=1.0') and 'deflated_sharpe' in txt]"
```
Expected: empty (no production call sites with factor=1.0 remain — except deliberate raw-Sharpe ones documented in code, which are OK and should have a comment).

- [ ] **Step 4: git status clean check**

Run: `git status --short`
Expected: only pre-existing modified artifacts (release_gate, experiment_registry) — no stray temp files.

- [ ] **Step 5: Update plan checklist — all done**

Mark every checkbox complete in this file.

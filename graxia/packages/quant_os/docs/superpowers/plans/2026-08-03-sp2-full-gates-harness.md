# SP2: Full Gates Harness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the kelly call bug unblocking institutional_pipeline Layer 2c+, and add WFA (purged-CV) + Bootstrap CI + MinBTL institutional gates to trial harnesses 1028 and 1032 (PBO = N/A by design for single frozen-config trials).

**Architecture:** Component A fixes the `compute_kelly` call to match the real signature (`win_loss_ratio`, `avg_loss`, drop `spread_cost`). Component B adds a shared `scripts/_trial_gates.py` helper that runs the 3 gates via existing `validation/` modules, wired into both harnesses after the DSR block, recorded in artifacts as additional evidence (DK remains primary gate).

**Tech Stack:** Python 3.12, pandas, numpy, pytest, pre-commit (ruff).

**Spec:** `docs/superpowers/specs/2026-08-03-sp2-full-gates-harness-design.md` (FINAL)

## Global Constraints

- Do NOT modify verdict rules — DK stays the primary gate; new gates are additional evidence.
- Do NOT fabricate PBO variants (single frozen-config trials — would be selection bias). Record PBO as N/A with reason.
- `compute_kelly` formula: f* = (b·p − q)/b; avg_loss only used as a >0 guard — pass 1.0.
- Existing tests must stay green: `test_ws_a_tsmom.py`, SP1 test files.
- Commit per task: `fix(quant_os): ...` / `feat(quant_os): ...`
- Workdir: `C:\Users\menum\graxia os\graxia\packages\quant_os`

---

### Task 1: Fix kelly call in institutional_pipeline

**Files:**
- Modify: `scripts/institutional_pipeline.py:281-285`

- [ ] **Step 1: Inspect the current call**

Read lines 272-295 of `scripts/institutional_pipeline.py`. Confirm the buggy call:
```python
kr = kelly_sizer.compute_kelly(
    win_rate=wr, avg_rr=rr,
    vol_current=vol_current, vol_target=0.15,
    regime="normal", spread_cost=0.001,
)
```

- [ ] **Step 2: Apply the fix**

Replace with:
```python
kr = kelly_sizer.compute_kelly(
    win_rate=wr,
    win_loss_ratio=rr,      # SP2: avg_rr → win_loss_ratio (real signature)
    avg_loss=1.0,           # SP2: required param; only used as >0 guard in formula
    current_vol=vol_current,
    regime="normal",
    # SP2: removed vol_target/spread_cost — not in compute_kelly signature
)
```

- [ ] **Step 3: Verify signature compatibility**

Run: `python -m py_compile scripts/institutional_pipeline.py`
Expected: exit 0

- [ ] **Step 4: Smoke run**

Run: `python scripts/institutional_pipeline.py > "$env:TEMP\t_sp2_kelly.txt" 2>&1`
Check the last lines — pipeline must now reach Layer 3+ (cost/capacity) or complete, with NO `TypeError` on `compute_kelly`.

- [ ] **Step 5: Commit**

```bash
git add scripts/institutional_pipeline.py
git commit -m "fix(quant_os): kelly compute_kelly call args (win_loss_ratio, avg_loss) — unblock Layer 2c"
```

---

### Task 2: Create `_trial_gates.py` helper (TDD)

**Files:**
- Create: `scripts/_trial_gates.py`
- Create: `tests/test_trial_gates.py`

**Interfaces:**
- Produces: `run_institutional_gates(portfolio_returns: pd.Series, returns_by_symbol: dict[str, pd.Series], observed_sharpe: float, n_trials: int, n_bars: int, annualization_factor: float = 252) -> dict` with keys: `wfa`, `bootstrap_ci`, `min_btl`, `pbo_na`, `combined_pass`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_trial_gates.py
"""Tests for _trial_gates.run_institutional_gates (SP2)."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("_trial_gates", str(_ROOT / "scripts" / "_trial_gates.py"))
_tg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_tg)


def _make_returns(seed: int = 42, n: int = 1500, n_syms: int = 3) -> tuple[pd.Series, dict[str, pd.Series]]:
    rng = np.random.default_rng(seed)
    d = {f"s{i}": pd.Series(rng.normal(0.0004, 0.01, n)) for i in range(n_syms)}
    port = pd.concat(d.values(), axis=1).mean(axis=1)
    return port, d


def test_gates_return_expected_keys():
    port, syms = _make_returns()
    r = _tg.run_institutional_gates(port, syms, observed_sharpe=1.2, n_trials=1050, n_bars=len(port))
    assert set(["wfa", "bootstrap_ci", "min_btl", "pbo_na"]).issubset(r.keys())
    assert r["pbo_na"]["reason"]  # non-empty reason string


def test_wfa_has_folds():
    port, syms = _make_returns()
    r = _tg.run_institutional_gates(port, syms, observed_sharpe=1.2, n_trials=1050, n_bars=len(port))
    assert r["wfa"]["n_folds"] == 5
    assert "oos_sharpe_mean" in r["wfa"]
    assert len(r["wfa"]["fold_sharpes"]) == 5


def test_bootstrap_ci_structure():
    port, syms = _make_returns()
    r = _tg.run_institutional_gates(port, syms, observed_sharpe=1.2, n_trials=1050, n_bars=len(port))
    ci = r["bootstrap_ci"]
    assert ci["lower"] < ci["upper"]
    assert "pass" in ci


def test_min_btl_structure():
    port, syms = _make_returns()
    r = _tg.run_institutional_gates(port, syms, observed_sharpe=1.2, n_trials=1050, n_bars=len(port))
    mb = r["min_btl"]
    assert "min_observations" in mb
    assert "sufficient" in mb


def test_insufficient_data_does_not_crash():
    port = pd.Series(np.random.default_rng(1).normal(0, 0.01, 60))
    r = _tg.run_institutional_gates(port, {"s0": port}, observed_sharpe=0.5, n_trials=10, n_bars=60)
    assert "status" in r or r["wfa"]["n_folds"] <= 5
```

- [ ] **Step 2: Run test — verify it fails**

Run: `python -m pytest tests/test_trial_gates.py -q`
Expected: FAIL with `ModuleNotFoundError` or `AttributeError` (helper missing)

- [ ] **Step 3: Write the helper**

```python
# scripts/_trial_gates.py
"""Institutional robustness gates for trial harnesses (SP2).

WFA (purged-CV) + Bootstrap CI + MinBTL.
PBO is intentionally NOT computed: WS-A trials are single frozen-config
pre-registrations with no parameter search space; PBO would measure search
bias that does not exist, and fabricating variants post-hoc would introduce
selection bias. Recorded as N/A with this reason.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent


def _load(mod_name: str, rel: str):
    spec = importlib.util.spec_from_file_location(mod_name, str(_ROOT / rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_institutional_gates(
    portfolio_returns: pd.Series,
    returns_by_symbol: dict[str, pd.Series],
    observed_sharpe: float,
    n_trials: int,
    n_bars: int,
    annualization_factor: float = 252,
) -> dict:
    """Compute WFA + Bootstrap CI + MinBTL for a trial harness.

    Args:
        portfolio_returns: Daily portfolio return series.
        returns_by_symbol: symbol -> daily signal-aligned returns.
        observed_sharpe: ANNUALIZED Sharpe of the portfolio.
        n_trials: Reconciled cumulative trial count (multiple testing).
        n_bars: Bar count (current observations for MinBTL).
        annualization_factor: Bars per year (252 for D1).

    Returns:
        dict with keys: wfa, bootstrap_ci, min_btl, pbo_na, combined_pass.
    """
    wf = _load("_wf", "validation/walk_forward.py")
    bs = _load("_bs", "validation/bootstrap_sensitivity.py")
    dsr = _load("_dsr", "validation/deflated_sharpe.py")

    # ── WFA: purged-CV time-split robustness of the signal ──────────────
    wfa_result: dict = {"n_folds": 0, "fold_sharpes": [], "oos_sharpe_mean": 0.0, "oos_sharpe_std": 0.0, "pass": False}
    n = len(portfolio_returns)
    if n >= 200:
        folds = list(wf.purged_cv(n, n_folds=5, embargo=12))
        fold_sharpes = []
        for _tr_idx, te_idx in folds:
            if len(te_idx) < 30:
                continue
            fold_ret = portfolio_returns.iloc[te_idx]
            sd = float(fold_ret.std())
            if sd > 0:
                fold_sharpes.append(float(fold_ret.mean() / sd * math.sqrt(annualization_factor)))
        if fold_sharpes:
            arr = np.array(fold_sharpes)
            wfa_result = {
                "n_folds": len(fold_sharpes),
                "fold_sharpes": [round(x, 4) for x in fold_sharpes],
                "oos_sharpe_mean": round(float(arr.mean()), 4),
                "oos_sharpe_std": round(float(arr.std(ddof=1)), 4),
                "pass": float(arr.mean()) > 0,
            }

    # ── Bootstrap CI on portfolio Sharpe ────────────────────────────────
    boot_result = {"lower": 0.0, "upper": 0.0, "pass": False}
    if len(portfolio_returns) >= 100:
        boot = bs.bootstrap_confidence_interval(
            portfolio_returns.tolist(), n_resamples=1000, confidence_level=0.95, seed=42
        )
        boot_result = {
            "lower": round(float(boot.confidence_interval_95[0]), 6),
            "upper": round(float(boot.confidence_interval_95[1]), 6),
            "pass": bool(boot.passes_threshold),
        }

    # ── MinBTL ──────────────────────────────────────────────────────────
    min_btl = dsr.min_backtest_length(
        observed_sharpe=observed_sharpe,
        n_trials=n_trials,
        sharpe_annualization_factor=math.sqrt(annualization_factor),
        current_observations=n_bars,
    )
    min_btl_result = {
        "min_observations": int(min_btl.min_observations),
        "sufficient": bool(min_btl.sufficient),
        "pass": bool(min_btl.sufficient),
    }

    pbo_na = {
        "value": None,
        "pass": None,
        "reason": (
            "PBO not applicable: WS-A trials are single frozen-config pre-registrations "
            "(no parameter search space). PBO measures search bias which does not exist; "
            "fabricating variants post-hoc would introduce selection bias."
        ),
    }

    gate_passes = [wfa_result["pass"], boot_result["pass"], min_btl_result["pass"]]
    return {
        "wfa": wfa_result,
        "bootstrap_ci": boot_result,
        "min_btl": min_btl_result,
        "pbo_na": pbo_na,
        "combined_pass": bool(sum(gate_passes) >= 2),
        "status": "OK",
    }
```

- [ ] **Step 4: Run test — verify it passes**

Run: `python -m pytest tests/test_trial_gates.py -q`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/_trial_gates.py tests/test_trial_gates.py
git commit -m "feat(quant_os): _trial_gates helper — WFA/bootstrap/MinBTL institutional gates"
```

---

### Task 3: Wire gates into harness 1028 + 1032

**Files:**
- Modify: `scripts/run_52week_high_1032.py` (after DSR block ~line 410)
- Modify: `scripts/run_ws_a_tsmom.py` (after DSR block ~line 495)

- [ ] **Step 1: Wire into run_52week_high_1032.py**

After the DSR block (after the `print(f"  DSR passes ...")` line and before `except`), insert:

```python
        # ── Institutional gates (SP2) ────────────────────────────────────
        _tg_spec = importlib.util.spec_from_file_location(
            "_trial_gates", str(_ROOT / "scripts" / "_trial_gates.py")
        )
        _tg_mod = importlib.util.module_from_spec(_tg_spec)
        _tg_spec.loader.exec_module(_tg_mod)
        gates = _tg_mod.run_institutional_gates(
            portfolio_returns=_port_df["return"],
            returns_by_symbol=returns_by_symbol,
            observed_sharpe=m["sharpe"],
            n_trials=n_trials,
            n_bars=len(_port_df),
        )
        print(f"  WFA (purged-CV 5f): mean={gates['wfa']['oos_sharpe_mean']:.3f} pass={gates['wfa']['pass']}")
        print(f"  Bootstrap CI: [{gates['bootstrap_ci']['lower']:.3f}, {gates['bootstrap_ci']['upper']:.3f}] pass={gates['bootstrap_ci']['pass']}")
        print(f"  MinBTL: min_obs={gates['min_btl']['min_observations']} sufficient={gates['min_btl']['sufficient']}")
        print(f"  PBO: N/A — {gates['pbo_na']['reason'][:80]}...")
        _gates = gates
    except Exception as e:
        print(f"  DSR computation failed: {e}")
        _gates = None
```

Then add to the artifact dict (before `"combined_verdict"`): `"gates": _gates,`

- [ ] **Step 2: Wire into run_ws_a_tsmom.py**

Same insertion after its DSR block (`print(f"  DSR passes ...")` at ~line 495), with `_port_df["return"]`, `returns_by_symbol`, `n_trials` — check the variable names in that harness (it already builds `returns_by_symbol` earlier). Add `"gates": _gates` to its artifact dict.

- [ ] **Step 3: Verify compile + re-run both harnesses**

Run:
```bash
python -m py_compile scripts/run_52week_high_1032.py scripts/run_ws_a_tsmom.py
python scripts/run_52week_high_1032.py > "$env:TEMP\t_sp2_1032.txt" 2>&1
python scripts/run_ws_a_tsmom.py > "$env:TEMP\t_sp2_1028.txt" 2>&1
```
Check outputs contain `WFA (purged-CV`, `Bootstrap CI`, `MinBTL`, `PBO: N/A` and both still end `PRIMARY GATE: FAIL` (verdicts unchanged).

- [ ] **Step 4: Verify artifacts have gates field**

Run: `python -X utf8 -c "import json; d=json.load(open('reports/trial_1032_52week_high_results.json')); print('gates' in d, d.get('gates',{}).get('wfa',{}).get('oos_sharpe_mean'))"`

- [ ] **Step 5: Commit**

```bash
git add scripts/run_52week_high_1032.py scripts/run_ws_a_tsmom.py reports/trial_1032_52week_high_results.json reports/ws_a_trial_1028.json
git commit -m "feat(quant_os): wire institutional gates into harness 1028+1032"
```

---

### Task 4: Final verification

- [ ] **Step 1: Full targeted test batch**

Run: `python -m pytest tests/test_trial_gates.py tests/test_dsr_from_annualized.py tests/test_ws_a_tsmom.py tests/test_min_btl.py tests/test_phase_5_statistical.py tests/test_phase_5_integration.py tests/test_overfitting_pipeline.py -q`
Expected: all PASS

- [ ] **Step 2: Smoke institutional_pipeline completes**

Run: `python scripts/institutional_pipeline.py > "$env:TEMP\t_sp2_pipe.txt" 2>&1` then check it reaches Layer 3+ with no `TypeError` (kelly fixed).

- [ ] **Step 3: git status clean (no stray files)**

Run: `git status --short` — only expected artifacts modified.

- [ ] **Step 4: Mark plan checkboxes complete**

# Gate Re-Baseline Backlog — Quarantined Failures (2026-08-07)

**Status**: All quarantined tests now SKIP (enforcement fixed 2026-08-07). This file
tracks the REAL bugs behind each quarantine — the "gate re-baseline" work that must
FIX the code so the skips can be lifted before expiry (2026-12-31).

**Verification**: `python -m pytest <the 8 files> -q` → exit 0 (42 skipped, 0 failed).
`tests/test_quarantine_integrity.py` → pass. Quarantine enforcement gap closed: the
manifest is now consistent with `@pytest.mark.skip` markers in code.

## The 8 real bugs to fix (in priority order)

### 1. QOS-RB-027 — `realistic_slippage_pips()` broken (6 tests, HIGH)
- **Evidence**: `Slippage 1.2337 exceeded cap 1.0`; median 0.667 (expected <0.4); mean 0.806 (expected 0.15-0.45)
- **Root cause hypothesis**: slippage now generated from spread model (slippage ≡ spread era, MEGA_PLAN F16 100x cost bug class) — distribution no longer half-normal with sigma=max*0.35
- **Files**: `execution/adapters/base.py::realistic_slippage_pips`, `tests/test_slippage_helper.py`
- **Fix bar**: cap at 2x max, half-normal(0, max*0.35) distribution, deterministic with seed

### 2. QOS-RB-030 — synthetic shock scenarios broken (20 tests, HIGH)
- **Evidence**: 19 of 20 fail alone; scenario registration/description/shock checks + convergence/recovery worse-than assertions + ScenarioResult field types
- **Files**: `backtest/` stress/shock modules + `tests/test_synthetic_shock_scenarios.py`
- **Fix bar**: re-baseline scenario registry + stress results against current shock model

### 3. QOS-RB-022 — XAUUSD dataset manifest checks fail (6 tests, MEDIUM)
- **Evidence**: checksums/timestamps/synthetic/timezone/source all fail for XAUUSD manifests
- **Files**: `data/` XAUUSD manifest files + `tests/test_phase_2a.py`
- **Fix bar**: regenerate/repair XAUUSD manifests with correct sha256, timestamps, source=MT5

### 4. QOS-RB-006 — deflated-Sharpe negative/zero assertions (2 tests, MEDIUM)
- **Files**: `validation/deflated_sharpe.py`, `tests/chaos/test_strategies_untested.py`
- **Fix bar**: verify DSR returns negative for Sharpe<=0 at N trials

### 5. QOS-RB-010 — ML pipeline predict() contract (2 tests, MEDIUM)
- **Files**: ML pipeline `predict`/`predict_payload` + `tests/test_comprehensive.py`
- **Fix bar**: settle return contract (tuple vs object) and update tests

### 6. QOS-RB-001 — API risk endpoints signature (4 tests, MEDIUM)
- **Files**: `api/risk.py` + `tests/chaos/test_api_untested.py`
- **Fix bar**: update chaos tests to pass `request`/`payload` args (FastAPI injection refactor)

### 7. QOS-RB-005 — RSS feed fetch (1 test, LOW)
- **Files**: news pipeline + `tests/chaos/test_full_pipeline.py`
- **Fix bar**: use offline fixture instead of live network

### 8. QOS-RB-028 — RiskBudget round-trip persistence (1 test, LOW)
- **Files**: `core/risk_budget.py` + `tests/test_state_persistence.py`
- **Fix bar**: restore save/load round-trip after risk_budget refactor

## Lift condition
Each fix is done when: code fixed → skip marker removed → manifest entry removed →
`tests/test_quarantine_integrity.py` still passes → full suite green for that file.

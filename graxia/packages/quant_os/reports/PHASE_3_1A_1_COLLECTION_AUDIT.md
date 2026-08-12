# Phase 3.1A.1 — Test Collection Audit (Workstream A)

**Date:** 2026-06-22
**Scope:** Fix all pytest collection errors across 7 test files

## Summary

| Test file | Error | Fix | Status | Notes |
|---|---|---|---|---|
| `test_timing2.py` | `TypeError: unsupported operand type(s) for *: 'float' and 'decimal.Decimal'` in `cost_model.py:44` | Added `from decimal import Decimal`; wrapped `commission_per_lot=Decimal("3.5")` and `initial_capital=Decimal("10000")` in BacktestConfig constructor | **ACTIVE** | Root cause: BacktestConfig accepts float for Decimal fields without coercion; cost_model multiplies float × Decimal |
| `test_vwap.py` | `TypeError: unsupported operand type(s)` from removed `risk_per_trade_pct` and `units_per_lot` config fields | Cannot fix — file is DEPRECATED and uses removed BacktestConfig fields | **QUARANTINED** | Already marked deprecated in file header; covered by `test_timing.py` which runs all 13 strategies including VWAPRejection |
| `test_phase_3b_regime.py` | `ModuleNotFoundError: No module named 'validation'` | Fixed import: `from validation.regime_analyzer` → `from graxia.packages.quant_os.validation.regime_analyzer` | **ACTIVE** | Module exists at correct path |
| `test_phase_3b_exit_gate.py` | `ModuleNotFoundError: No module named 'validation'` | Fixed imports: `from validation.exit_gate` and `from validation.regime_analyzer` → fully qualified paths | **ACTIVE** | Module exists at correct path |
| `test_phase_3_3_news_events.py` | `ModuleNotFoundError: No module named 'news_events'` | Fixed all `from news_events.xxx` imports → `from graxia.packages.quant_os.news_events.xxx`; fixed bare `import news_events` and `open("news_events/...")` file paths to use `os.path` relative to test file | **ACTIVE** | Import isolation tests now resolve source files via `os.path.dirname(__file__)` |
| `test_repo_manifest.py` | `ModuleNotFoundError: No module named 'repo_intelligence'` | Fixed import: `from repo_intelligence.manifest` → `from graxia.packages.quant_os.repo_intelligence.manifest` | **ACTIVE** | Module exists at correct path |
| `test_supply_chain.py` | `ModuleNotFoundError: No module named 'repo_intelligence'` | Fixed import: `from repo_intelligence.supply_chain` → `from graxia.packages.quant_os.repo_intelligence.supply_chain` | **ACTIVE** | Module exists at correct path |

## Verification Results

All 6 ACTIVE files pass collection (`python -c "import ..."` exits 0):

```
test_timing2.py          ✅ OK (runs all 13 strategies, completes in ~1.5s)
test_phase_3b_regime.py  ✅ OK
test_phase_3b_exit_gate.py ✅ OK
test_phase_3_3_news_events.py ✅ OK
test_repo_manifest.py    ✅ OK
test_supply_chain.py     ✅ OK
test_vwap.py             ⏸️  QUARANTINED — uses removed config fields
```

## Fixes Applied

### test_timing2.py (ACTIVE)
- Added `from decimal import Decimal` import
- Changed `initial_capital=10000` → `initial_capital=Decimal("10000")`
- Changed `commission_per_lot=3.5` → `commission_per_lot=Decimal("3.5")`

### test_phase_3b_regime.py (ACTIVE)
- `from validation.regime_analyzer` → `from graxia.packages.quant_os.validation.regime_analyzer`

### test_phase_3b_exit_gate.py (ACTIVE)
- `from validation.exit_gate` → `from graxia.packages.quant_os.validation.exit_gate`
- `from validation.regime_analyzer` → `from graxia.packages.quant_os.validation.regime_analyzer`

### test_phase_3_3_news_events.py (ACTIVE)
- All 6 `from news_events.xxx` imports → `from graxia.packages.quant_os.news_events.xxx`
- `import news_events` → `import graxia.packages.quant_os.news_events`
- `open(f"news_events/{fname}")` → `open(os.path.join(pkg_dir, fname))` using `pkg_dir = os.path.join(os.path.dirname(__file__), "..", "news_events")`
- Added `import os`

### test_repo_manifest.py (ACTIVE)
- `from repo_intelligence.manifest` → `from graxia.packages.quant_os.repo_intelligence.manifest`

### test_supply_chain.py (ACTIVE)
- `from repo_intelligence.supply_chain` → `from graxia.packages.quant_os.repo_intelligence.supply_chain`

## Root Cause Pattern

Most errors (5 of 7) were **bare imports** — tests imported `validation`, `news_events`, or `repo_intelligence` as top-level modules instead of using fully qualified `graxia.packages.quant_os.*` paths. This works when `sys.path` includes the package root but fails under standard pytest collection.

The Decimal/float issue in `test_timing2.py` stems from `BacktestConfig` using `Decimal` type annotations but accepting raw `float`/`int` without coercion. The `cost_model.py` then multiplies the unconverted float with a `Decimal`, which Python forbids. The test fix is correct; a deeper fix would be adding `__post_init__` coercion to `BacktestConfig`.

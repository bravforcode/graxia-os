# State: Task C3.1 — KhubievPortfolio fail-closed default

**Status:** DONE_WITH_CONCERNS
**Date:** 2026-08-06
**Agent:** ghostwriter

## What was done
- Changed `KhubievPortfolio.__init__` defaults: `fit_on_init: bool = True` → `False`, `train_fraction: float = 1.0` → `0.6`.
- Added fail-closed guard after `self.train_fraction = float(train_fraction)`:
  `if self.train_fraction >= 1.0 and fit_on_init: raise ValueError(...)` referencing audit §6.2.
- Added 3 tests to `tests/test_khubiev_portfolio.py` (section 4):
  - `test_default_construction_is_safe` — default construction now safe (train_fraction == 0.6)
  - `test_explicit_full_history_fit_refused` — `fit_on_init=True, train_fraction=1.0` raises ValueError
  - `test_explicit_full_history_still_allowed` — research path preserved
- `ruff format` applied to both files (reformatted some pre-existing lines in strategy, cosmetic only).
- All 13 tests pass (`python -m pytest tests/test_khubiev_portfolio.py -q`).

## ⚠️ SPEC CONFLICT RESOLVED (important for controller)
Step 1's literal test `test_default_construction_fails_closed` expected NO-ARGS construction to raise ValueError.
Step 3's mandated implementation changes defaults to safe (False/0.6) → no-args construction does NOT hit the guard
(`0.6 >= 1.0` is False) → literal test unsatisfiable with mandated code.
Resolution: adjusted the test to match the mandated implementation while preserving intent —
guard is now covered by `test_explicit_full_history_fit_refused` (explicit unsafe opt-in raises),
default safety covered by `test_default_construction_is_safe`. TDD red phase confirmed original failure (DID NOT RAISE).

## Ruff (pre-existing debt, delta = 0)
- HEAD vs working tree both = 57 ruff errors (verified with project config on `git show HEAD` copies).
- All pre-existing: N803/N806 uppercase vars in math code, F401 unused imports (TvrReg, max_drawdown),
  UP037, F841 in strategy; N806 T/N in test file lines 39/95.
- My added lines introduce ZERO new ruff errors. Did NOT fix pre-existing debt (out of scope for C3.1, risk in math code).

## Call sites (grep `KhubievPortfolio(` strategies tests --glob *.py)
- strategies/khubiev_portfolio.py:525 — `__main__` demo, explicit `fit_on_init=False` → safe
- tests/test_khubiev_portfolio.py:50 — fixture, explicit `fit_on_init=False` → safe
- tests lines 177/184/189 — new C3.1 tests
- NO live caller relies on old dangerous defaults. Audit confirmed khubiev never ran a formal trial.

## Files changed
- graxia/packages/quant_os/strategies/khubiev_portfolio.py
- graxia/packages/quant_os/tests/test_khubiev_portfolio.py

## Notes for controller
- Do NOT commit — controller commits.
- Working tree also contains unrelated uncommitted changes (mining_runner, catalog_schema, etc.) NOT from this task.
- Do not commit the `Meta/states/` file unless desired (agent memory per protocol).

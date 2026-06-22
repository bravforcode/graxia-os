# G0 Test Census Reconciliation

## Canonical current full-suite command

```powershell
python -m pytest graxia/packages/quant_os/tests/ -q --tb=line
```

## Canonical current collection command

```powershell
python -m pytest graxia/packages/quant_os/tests/ --collect-only -q
```

## Current verified census
- Source bundle: `artifacts/release_truth/20260622_201422`
- Collected: `745`
- Executed result: `744 passed, 1 skipped`
- Quarantined skip: `tests/test_vwap.py`

## Why this differs from other numbers
- `745 / 744+1` comes from `scripts/run_release_truth.py`, which targets `graxia/packages/quant_os/tests/` only.
- `563 / 562+1` in older Phase 3.1A.2 artifacts comes from the release-gate lane, which explicitly ignores `test_vwap.py`.
- A broader package-root sweep such as `python -m pytest graxia/packages/quant_os/ --collect-only -q` includes module-local `test_*.py` files outside top-level `tests/` and produces a much larger census. On the current snapshot it is larger than `745` and not equivalent.

## 1186 status
- No current workspace artifact proving a literal `1186 passed` or `1186 collected` was found during this Phase 0A run.
- Treat `1186` as unverified historical output until a preserved artifact is produced.

## Required rule going forward
- Do not compare counts across different pytest roots.
- Every future release-truth bundle must preserve:
  - `collect_command.txt`
  - `pytest_command.txt`
  - `test_collection.json`
  - `pytest_output.txt`
  - `results.json`

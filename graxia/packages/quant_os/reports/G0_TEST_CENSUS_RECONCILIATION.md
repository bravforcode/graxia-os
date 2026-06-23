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
- Canonical command root: monorepo root
- Verified isolated worktree: `C:\tmp\quant_os_phase0a_verify`
- Verified commit: `6f5500d103462944b7f857c93c3c6ed6de4e97ee`
- Source bundle: `C:\tmp\quant_os_phase0a_verify\artifacts\release_truth\20260622_204920`
- Collected: `740`
- Executed result: `2 collection errors`
- Blocking imports:
  - `graxia/packages/quant_os/tests/test_phase_9_integration.py`
  - `graxia/packages/quant_os/tests/test_phase_9_review.py`
- Exact error:
  - `ModuleNotFoundError: No module named 'graxia.packages.quant_os.canary.review'`

## Why this differs from other numbers
- `740 / 2 errors` is the current clean-worktree truth for pinned commit `6f5500d103462944b7f857c93c3c6ed6de4e97ee`.
- Earlier branch-local bundle `artifacts/release_truth/20260622_201422` recorded `745 / 744+1` on a different branch snapshot and must not be treated as equivalent.
- `563 / 562+1` in older Phase 3.1A.2 artifacts comes from the release-gate lane, which explicitly ignores `test_vwap.py`.
- Non-canonical package-root sweeps from inside `graxia/packages/quant_os` are not comparable to the monorepo-root command above.

## 1186 status
- No current workspace artifact proving a literal `1186 passed` or `1186 collected` was found during this Phase 0A run.
- Treat `1186` as unverified historical output until a preserved artifact is produced.

## Required rule going forward
- Do not compare counts across different pytest roots.
- Do not compare counts across different commits or dirty-vs-clean worktrees.
- Every future release-truth bundle must preserve:
  - `collect_command.txt`
  - `pytest_command.txt`
  - `test_collection.json`
  - `pytest_output.txt`
  - `results.json`

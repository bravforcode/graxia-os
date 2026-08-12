# Provenance Stabilization Plan

## Current Branch

- `staging`

## Dirty Diff Summary

- Dirty entries observed from `git status --porcelain=v1`: `379`
- Staged entries observed from `git diff --cached --name-status`: `27`
- `git diff --stat` still reports `231 files changed, 19730 insertions(+), 11776 deletions(-)`
- Worktree mixes product changes, tests, docs, migrations, generated files, virtualenv/vendor churn, and local artifacts.

## Tracked Artifact Findings

- Tracked artifact paths observed in diff:
  - `.venv/Scripts/python.exe`
  - `.venv/Scripts/pythonw.exe`
  - `backend/venv/**`
  - `backend/openapi.json`
- Untracked local artifact paths observed:
  - `.hypothesis/`
  - `backend/.hypothesis/`
  - `frontend/storageState.json`
  - `backups/`
  - `nul`
  - `backend/nul`
- Secret-like untracked path observed:
  - `.env.development`

## Ignore Rule Findings

- `node_modules` is ignored by `.gitignore`.
- `.venv/` and `backend/venv/` ignore rules exist, but tracked files under those paths are already in git history/index.
- `backend/openapi.json` is listed in `.gitignore`, but it is still tracked and therefore still appears in diffs.
- Missing or incomplete ignore coverage should be documented before any cleanup:
  - `.env.*` pattern with `!.env.example`
  - `.mypy_cache/`
  - `.ruff_cache/`
  - `coverage/`

## Safe Cleanup Options

### Option A — Report only, no cleanup

- Preserve all current changes.
- Proceed only with docs/classification.
- Safest if the user wants zero index changes right now.

### Option B — Add/update `.gitignore` only

- Add missing ignore rules.
- Does not remove already tracked artifacts from git index.
- Safe but insufficient on its own.

### Option C — Remove tracked artifacts from git index after user approval

- Target only tracked artifacts such as `.venv/`, `backend/venv/`, and generated files like `backend/openapi.json` if approved.
- Must be done in a dedicated hygiene commit, separate from product work.

### Option D — Archive current state before cleanup

- Create a safety snapshot/branch/commit after user approval.
- Then perform targeted index cleanup in a separate follow-up step.

## Recommended Option

- Recommended path: `Option A` now, then `Option D`, then `Option C` after explicit user approval.
- Reason: current diff mixes real product work with tracked vendor churn, so cleanup without a preserved checkpoint risks losing attribution.

## Exact Commands To Run Later

```powershell
git switch -c phase1/hygiene-stabilization
# after user approval for tracked artifact cleanup only
git rm -r --cached -- .venv backend/venv
# optional only if generated spec should not stay tracked
git rm --cached -- backend/openapi.json
# then patch .gitignore if approved
```

## Commands Not Run In This Phase

- `git rm -r --cached -- .venv backend/venv`
- `git rm --cached -- backend/openapi.json`
- `git add .`
- `git reset --hard`
- `git clean -fd`
- any commit/push command

## Risks

- Secret-like env files exist untracked and must not be accidentally committed.
- Tracked vendor artifacts currently obscure code review and regression attribution.
- Cleanup before preserving legitimate product changes may collapse unrelated work into one risky change set.

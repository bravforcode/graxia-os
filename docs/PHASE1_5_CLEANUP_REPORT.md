# Phase 1.5 Cleanup Report

## 1. Verdict

PASS

## 2. Cleanup Scope Approved

- stop tracking `.venv/**`
- stop tracking `backend/venv/**`
- stop tracking `backend/openapi.json`
- add ignore rules for `.env.*`
- add ignore rules for `.mypy_cache/`
- add ignore rules for `.ruff_cache/`
- add ignore rules for `coverage/`

## 3. What Was Changed

- `.gitignore`:
  - added `.env.*`
  - added `!.env.example`
  - added `.mypy_cache/`
  - added `.ruff_cache/`
  - added `coverage/`
- git index:
  - removed tracked `.venv/**` from git index with `git rm -r --cached .venv`
  - removed tracked `backend/venv/**` from git index with `git rm -r --cached backend/venv`
  - removed tracked `backend/openapi.json` from git index with `git rm --cached backend/openapi.json`
  - removed pre-existing staged product files from the index stage only with exact `git restore --staged ...` paths
- docs:
  - created `docs/PRE_CLEANUP_SNAPSHOT.md`
  - created `docs/PHASE1_5_CLEANUP_REPORT.md`

## 4. What Was Not Changed

- implementation code: not changed
- agent-stack import: not performed
- migrations: not changed
- frontend source: not changed
- backend logic: not changed

## 5. Files Removed From Git Index

| Path | Local file still exists? | Reason |
|---|---:|---|
| `.venv/**` | yes | local virtualenv artifact should not be tracked |
| `backend/venv/**` | yes | vendor/local virtualenv artifact should not be tracked |
| `backend/openapi.json` | yes | generated API artifact should not be tracked |

## 6. Ignore Rules Added

- `.env.*`
- `!.env.example`
- `.mypy_cache/`
- `.ruff_cache/`
- `coverage/`

## 7. Verification Commands

- `git ls-files .venv`: tracked before cleanup, then removed from index
- `git ls-files backend/venv`: tracked before cleanup, then removed from index
- `git ls-files backend/openapi.json`: tracked before cleanup, then removed from index
- `cmd /c if exist .venv (echo True) else echo False`: `True`
- `cmd /c if exist backend\venv (echo True) else echo False`: `True`
- `cmd /c if exist backend\openapi.json (echo True) else echo False`: `True`

## 8. Current Dirty Worktree After Cleanup

- cached cleanup diff now contains only:
  - `.venv/**` deletion-from-index
  - `backend/venv/**` deletion-from-index
  - `backend/openapi.json` deletion-from-index
  - `.gitignore`
  - cleanup/docs files that are explicitly staged in this phase
- non-cleanup product changes still remain in the working tree and were intentionally left unstaged for this commit

## 9. Remaining Product Changes To Preserve

- backend API/auth/MCP/model/test changes remain in the working tree
- frontend source/UI changes remain in the working tree
- additional docs, scripts, migrations, and untracked feature work remain outside this cleanup commit

## 10. Tests

- not run
- reason:
  - Phase 1.5 is cleanup-only
  - running tests/builds here can create more artifacts in an already dirty worktree
  - this phase only stabilizes tracking/ignore hygiene

## 11. Safety Review

- `.env` read: no
- secrets printed: no
- local files deleted: no
- implementation changed: no
- agent-stack imported: no
- `git add .` used: no
- live provider called: no

## 12. Recommended Next Step

Phase 2 — preserve/commit existing product changes or create shared-contract compatibility branch

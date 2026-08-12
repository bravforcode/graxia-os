# Pre-Cleanup Snapshot

## Branch

`staging`

## Dirty Summary

- `git diff --stat`: `231 files changed, 19730 insertions(+), 11776 deletions(-)`
- `git status --porcelain=v1`: dirty worktree remains mixed across product source, tests, docs, frontend, `.venv/`, `backend/venv/`, and generated artifacts
- `git diff --cached --name-status`: staged product changes already exist and must be excluded from this cleanup commit

## Approved Cleanup Scope

- stop tracking `.venv/**`
- stop tracking `backend/venv/**`
- stop tracking `backend/openapi.json`
- add ignore rules for `.env.*`
- add ignore rules for `!.env.example`
- add ignore rules for `.mypy_cache/`
- add ignore rules for `.ruff_cache/`
- add ignore rules for `coverage/`

## Files/Patterns To Stop Tracking

- `.venv/**`
- `backend/venv/**`
- `backend/openapi.json`

## Ignore Rules To Add

- `.env.*`
- `!.env.example`
- `.mypy_cache/`
- `.ruff_cache/`
- `coverage/`

## Commands Planned But Not Yet Run

```powershell
git ls-files .venv
git ls-files backend/venv
git ls-files backend/openapi.json
git rm -r --cached .venv
git rm -r --cached backend/venv
git rm --cached backend/openapi.json
git restore --staged <exact product paths only if still staged>
git add .gitignore
git add docs/PRE_CLEANUP_SNAPSHOT.md
git add docs/PHASE1_5_CLEANUP_REPORT.md
git commit -m "chore: stabilize merge hygiene and stop tracking local artifacts"
```

## Safety Notes

- no `.env` read
- no local file deletion
- no implementation changes
- no `agent-stack` import

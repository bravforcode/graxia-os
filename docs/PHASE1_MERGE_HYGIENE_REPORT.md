# Phase 1 Merge Hygiene Report

## 1. Verdict

BLOCKED

## 2. Current Repo State

- root: `C:\Users\menum\graxia os`
- branch: `staging`
- dirty entries: `379`
- dirty files per `git diff --stat`: `231`
- tracked artifacts: `.venv/**`, `backend/venv/**`, `backend/openapi.json`
- untracked artifacts: `.hypothesis/`, `backend/.hypothesis/`, `frontend/storageState.json`, `backups/`, `nul`, `backend/nul`
- secret risk: untracked `.env.development` plus partially ignored `.env.*` family

## 3. What Was Done

- read-only classification: complete
- provenance plan: complete
- crosswalk plan: complete
- tests run: none

## 4. Files Created

- `docs/DIRTY_WORKTREE_CLASSIFICATION.md`
- `docs/PROVENANCE_STABILIZATION_PLAN.md`
- `docs/SHARED_CONTRACT_CROSSWALK_PLAN.md`
- `docs/PHASE1_MERGE_HYGIENE_REPORT.md`

## 5. Files Modified

- docs only? yes
- `.gitignore` modified? no

## 6. Dirty Worktree Classification Summary

- A. Product Source Changes: `112`
- B. Test Changes: `34`
- C. Documentation Changes: `29`
- D. Migration / Schema Changes: `8`
- E. Frontend Source Changes: `57`
- F. Generated Artifacts: `3`
- G. Virtualenv / Dependency / Vendor Artifacts: `111`
- H. Runtime / Cache / Log Artifacts: `8`
- I. Unknown / Requires Human Review: `17`

## 7. Tracked Artifact Findings

- `.venv/` and `backend/venv/` are already tracked in git diff.
- `.gitignore` already contains ignore rules for those paths, so ignore rules alone will not remove them.
- `backend/openapi.json` is also tracked even though `.gitignore` lists it.

## 8. Recommended Cleanup Strategy

- Do not cleanup in-place during this phase.
- Preserve the current state first.
- After approval, run targeted `git rm --cached` only for tracked artifacts in a dedicated hygiene step.
- Keep product source, frontend source, tests, and migrations separate from artifact cleanup.

## 9. Shared Contract Crosswalk Summary

- Graxia remains primary for `ApprovalRequest`, MCP response schema, workflow run schema, context engine, and health/readiness APIs.
- Agent-stack remains donor/reference for runtime envelopes, dispatch/audit patterns, and context-pipeline concepts.
- First future import target should be contracts only, not runtime apps.

## 10. Do-Not-Merge-Yet List

- do not import any `agent-stack` code yet
- do not root-merge workspaces
- do not cleanup tracked artifacts without approval
- do not run artifact-producing tests/builds during hygiene

## 11. Safe Next Phase

- approval-driven cleanup/prep step before any runtime import
- then shared-contract compatibility design/implementation

## 12. Exact User Decision Needed

- approve removing tracked `.venv/` and `backend/venv/` from git index later?
- approve treating `backend/openapi.json` as generated and removing it from git index later?
- approve adding missing `.gitignore` rules for `.env.*`, `.mypy_cache/`, `.ruff_cache/`, and `coverage/`?
- approve preserving current product changes in a dedicated checkpoint before cleanup?

## 13. Stop Conditions

- stop if secret-like env files need handling beyond ignore/reporting
- stop if cleanup would mix with user product work in the same commit
- stop before any runtime import until artifact cleanup decisions are approved

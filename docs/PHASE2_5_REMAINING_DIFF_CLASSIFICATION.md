# Phase 2.5 Remaining Diff Classification

| Path | Status | Bucket | Commit group | Risk | Action |
|---|---|---|---|---|---|
| `extraterrestrial-escape/` | `??` | `H. Local-only/unknown` | none | high | needs user decision |
| `sites/` | `??` | `H. Local-only/unknown` | none | high | needs user decision |
| `backend/nul` | ignored local artifact | `H. Local-only/unknown` | `.gitignore` cleanup | low | ignore |
| `nul` | ignored local artifact | `H. Local-only/unknown` | `.gitignore` cleanup | low | ignore |
| `frontend/storageState.json` | ignored local artifact | `H. Local-only/unknown` | `.gitignore` cleanup | low | ignore |
| `.agents/` | ignored local artifact | `H. Local-only/unknown` | `.gitignore` cleanup | low | ignore |
| `.planning/` | ignored local artifact | `H. Local-only/unknown` | `.gitignore` cleanup | low | ignore |
| `LEAN-CTX.md` | ignored local artifact | `H. Local-only/unknown` | `.gitignore` cleanup | low | ignore |

## Resolution Summary

- committed: stray tracked deleted path via `6d1950d chore: remove stray accidental tracked path`
- committed: backend runtime/content/knowledge lane via `26bb0fd feat: preserve runtime content and knowledge backend changes`
- committed: migration/schema lane via `ec96f18 feat: preserve staging migration and schema changes`
- committed: remaining backend tests via `b7eb8f6 test: preserve remaining backend runtime and staging coverage`
- committed: local-only ignore rules via `2b22187 chore: ignore local-only agent and test artifacts`
- committed: CI/config lane via `4490719 chore: preserve staging CI and configuration updates`
- committed: scripts/ops lane via `0761a7f chore: preserve remaining ops and readiness scripts`
- committed: docs lane via `f8ac814 docs: preserve staging and agent operation documentation`

## Current Conclusion

- no tracked dirty product files remain
- only untracked unknown subprojects remain: `extraterrestrial-escape/`, `sites/`
- these are not safe to auto-ignore or auto-commit because both look like real Astro projects, not cache/generated output

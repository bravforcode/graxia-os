# Phase 2 Commit Strategy

| Commit | Purpose | Paths | Tests before/after | Risk | Can commit now? |
|---|---|---|---|---|---|
| `P2-docs` | record remaining diff classification and plan | `docs/PHASE2_*`, `docs/_phase2_tmp/*` | none / doc-only | Low | Yes |
| `A1+B1` | preserve auth, health, audit, approval-org-scope baseline | `backend/app/api/auth.py`, `backend/app/api/router.py`, `backend/app/api/system.py`, `backend/app/api/audit.py`, `backend/app/api/health.py`, `backend/app/auth/**`, `backend/app/middleware/auth.py`, `backend/app/middleware/security.py`, `backend/app/models/approval_request.py`, matching tests | `python -m compileall backend/app`; targeted auth/health/audit tests | High | Maybe |
| `A3+B3` | preserve bootstrap, event bus, knowledge/runtime changes | `backend/app/core/bootstrap.py`, `backend/app/core/event_bus.py`, `backend/app/core/rag.py`, `backend/app/core/unit_of_work.py`, `backend/app/services/knowledge_service.py`, related tests | `python -m compileall backend/app`; targeted runtime tests | High | Maybe |
| `A4+E2` | preserve content-engine/social/research backend + required migrations | `backend/app/agents/social/*`, `backend/app/api/content_engine.py`, `backend/app/models/content_engine.py`, `backend/app/services/content_engine_service.py`, `backend/app/tasks/content_engine_tasks.py`, `backend/alembic/versions/019*`, `020*`, merge-head migrations | `python -m compileall backend/app`; `alembic heads`; targeted tests if present | High | Maybe |
| `C1+C2+D1+D2` | preserve frontend operator UI and build/test config | `frontend/src/**`, `frontend/package.json`, `frontend/vite.config.ts`, `frontend/playwright.config.ts`, `frontend/tailwind.config.js`, `frontend/tests/**`, `frontend/e2e/**` | `bun run build`; relevant frontend tests if stable | High | Maybe |
| `F1+F2+F3+F4` | preserve CI/ops/staging scripts/compose changes | `.github/workflows/**`, `scripts/**`, `backend/scripts/**`, `config/**`, `docker-compose.yml`, `.env.example`, `vercel.json`, `Makefile` | script syntax check where possible | High | Maybe |
| `G1` | preserve docs/reports/root guidance | `README.md`, `AGENTS.md`, `CLAUDE.md`, `docs/**`, `04-Archive/**` | none / doc-only | Low | Yes |
| `I1` | suspicious path handling | `"ersmenumgraxia os\\357\\200\\242 && git status"`, `backend/nul`, `nul` | none | High | No |

## Notes
- Do not mix suspicious paths into product commits.
- Do not stage `.env.*`, local caches, `.hypothesis/`, `backups/`, `.planning/`, `.agents/`.
- `backend/requirements.txt` remains held until backend feature grouping is clearer.
- If `python -m compileall backend/app` fails on current diff, stop backend preservation and report blocker instead of force-fixing broadly.
- If `bun run build` fails on current diff, stop frontend preservation and report blocker instead of broad UI edits.

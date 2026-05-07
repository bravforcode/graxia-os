# Agent Guide

Read this file first when continuing work in this repository.

Verified against live code on `2026-04-09`.

## Mission

Personal OS is a single-user control plane that:

- discovers opportunities, jobs, contacts, and email-driven work
- scores and prioritizes them
- drafts internal or user-facing artifacts
- tracks readiness, costs, and system health
- requires explicit approval before external actions

## Trust Order

When sources disagree, use this order:

1. Live code in `backend/` and `frontend/`
2. `README.md`
3. `agent.md`
4. Planning docs such as `CODEX_HANDOFF.md`, `AGENT_IMPLEMENTATION_GUIDE.md`, and `PHASE_2_FRONTEND_SPEC.md`

If a planning doc conflicts with the code, follow the code and then fix the stale doc.

## Current Truth

- Canonical backend: FastAPI app in `backend/app/main.py`
- Canonical API surface: REST endpoints under `/api/v1`
- Canonical frontend: React 18 + Vite + TypeScript in `frontend/`
- Legacy UI: `dashboard/` exists but is not mounted by the current backend runtime
- LLM runtime: `backend/app/core/llm.py` uses OpenClaw/Claude as primary and Gemini as fallback
- Runtime readiness modes: `full`, `degraded`, `blocked`
- Readiness bootstrap: `backend/app/core/bootstrap.py`
- Cross-agent transport: `backend/app/core/event_bus.py`
- Config surface: `backend/app/config.py`
- Approval handling exists and is part of the operational flow; external actions must stay gated
- Canonical test suite: `backend/tests/`
- Legacy/generated tests: `backend/tests_legacy/` are reference material, not default acceptance criteria

## Do Not Assume

Do not claim these are live unless you implement and verify them in code:

- Ollama or Together.ai as the active LLM path
- the old static dashboard as the current UI
- WebSocket agent streaming from `backend/app/main.py`
- legacy tests as proof of current behavior

## Non-Negotiables

- Preserve the single-user architecture.
- Patch incrementally; do not rewrite the system.
- Keep cross-agent communication on `EventBus`.
- Keep degraded mode honest instead of masking missing dependencies.
- Keep explicit approval before outreach, submission, or any other external side effect.
- Use `frontend/` for product UI work unless the task explicitly targets the legacy `dashboard/`.
- Assume the worktree may contain in-progress user changes; do not revert unrelated edits.

## Working Map

- `backend/app/agents/`: agent logic
- `backend/app/api/`: REST endpoints
- `backend/app/core/`: bootstrap, event bus, LLM, monitoring, runtime state
- `backend/app/models/`: persistence models
- `backend/app/schemas/`: API and domain contracts
- `backend/tests/`: current smoke/API contract tests
- `frontend/src/`: React application
- `identity/`: profile and personalization context
- `docs/superpowers/`: plans and specs that may be partially aspirational

## Safe Workflow

1. Read the relevant implementation path before editing.
2. Check `README.md` for the currently verified command path.
3. When docs and code diverge, trust code first.
4. Keep API changes aligned with existing response shapes.
5. Run the smallest meaningful verification after each substantial edit.

## Verification Commands

```bash
make infra-up
make migrate-local
make run-local
make frontend-dev
```

```bash
cd backend
python -c "from app.main import app; print(app.title)"
python -m pytest tests -q
```

```bash
cd frontend
bun run lint
bun run build
```

## Common Mistakes

- Editing `dashboard/` for current product work
- Treating planning docs as already implemented
- Running `backend/tests_legacy/` as the acceptance suite
- Describing AI routing features that are not present in `backend/app/core/llm.py`
- Turning optional local dependencies into hard startup failures without intent

## Deliverable Standard

Each change should improve at least one of these:

- runtime correctness
- operator visibility
- safer approval flow
- auditability
- documentation accuracy
- verification confidence

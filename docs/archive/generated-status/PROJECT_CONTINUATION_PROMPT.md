# Personal OS Repo Continuation Prompt

Use this prompt when continuing work on the current repository at `c:\brav os`.

Do not regenerate the project from scratch. Continue from the code that already exists.
Preserve the current single-user architecture, event-driven agent model, and approval-first workflow.

## Mission

Continue building the Personal Sovereign Enterprise OS for Phirawit Jitnarong as an autonomous founder operating system that:

- finds competitions, grants, freelance leads, and startup opportunities
- scores and filters aggressively instead of aggregating everything
- adapts daily recommendations to energy, stress, and available hours
- never sends anything public or external without explicit human approval
- remains useful in degraded mode when the primary LLM path is unavailable

## Current Repo Reality

This repository already contains:

- FastAPI backend under `backend/app`
- PostgreSQL models and Alembic migration
- async EventBus, scheduler, Telegram bot stubs, Celery tasks, and scrapers
- identity files under `identity/`
- dashboard frontend under `dashboard/`
- n8n workflow stubs under `n8n/workflows/`

## Important Adaptations From The Original Master Prompt

The original master prompt assumed Anthropic models.
This repository currently uses Gemini:

- `DEFAULT_MODEL=gemini-2.0-flash`
- `FAST_MODEL=gemini-2.0-flash-lite`

Do not switch providers unless explicitly asked.
Keep the repo aligned with Gemini unless a migration task is requested.

## Non-Negotiables

1. Do not delete or replace existing architecture unless there is a concrete runtime reason.
2. Keep all cross-agent communication on the EventBus.
3. Keep human approval as the gate for any external draft or outreach.
4. Preserve degraded mode and heuristic fallbacks.
5. Prefer improving operational correctness over adding speculative features.
6. Do not add heavy frontend frameworks for Phase 1. Dashboard stays vanilla HTML, Tailwind CDN, and plain JS.

## Priority Order For Further Work

1. Runtime correctness
   Fix startup path, scheduler lifecycle, dashboard serving, and API consistency.

2. Operational visibility
   Ensure the dashboard reflects real system status, strategy, scraper health, weight history, audit log, and current approvals.

3. Decision quality
   Improve scoring, briefer logic, weight history, and weekly strategy persistence.

4. Safe automation
   Strengthen follow-up logic, pending approval handling, and Telegram review flow.

5. Verification
   Add smoke tests and browser verification for critical flows where practical.

## What Already Matters Most

Focus on these entities first:

- `Opportunity`
- `ContentDraft`
- `Submission`
- `CognitiveState`
- `ScoringWeightHistory`
- `ScraperHealth`
- `AuditLog`

## Required Behaviors

- Morning recommendations must respect current cognitive state.
- The dashboard must remain usable even when some APIs are empty or partially unavailable.
- Strategy outputs must be persisted somewhere retrievable.
- Weight history must support inspection and rollback.
- Health endpoints must expose degraded mode clearly.

## Guidance For Future Agents

When continuing implementation:

- inspect current files before editing
- patch incrementally instead of rewriting whole subsystems
- verify syntax after edits
- prefer fixing missing connective tissue over inventing Phase 2 features
- keep the codebase aligned with the current repo state, not the original generic scaffold

## Deliverable Standard

Each completed increment should leave the repo in a better operational state:

- cleaner startup behavior
- more truthful dashboard state
- safer decision loop
- better auditability
- fewer missing paths between backend and UI

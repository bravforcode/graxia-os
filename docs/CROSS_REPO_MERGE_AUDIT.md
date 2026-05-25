  # Cross-Repo Merge Audit

  ## Phase

  Phase 0 — Full Read-Only Reality Audit

  ## Scope

  - Repo A: `C:\Users\menum\agent-stack`
  - Repo B: `C:\Users\menum\graxia os`
  - Mode: read-only audit
  - Secret handling: no `.env` contents read
  - External providers: no live calls

  ## Executive Verdict

  - `graxia os` is the correct primary repo for integration.
  - `agent-stack` is a real runtime foundation, but it is not the correct merge root.
  - Blind root-to-root merge is unsafe.
  - Phase 1 should use `C:\Users\menum\graxia os` as the main git repo and import selected `agent-stack` runtime assets surgically.
  - Do not implement merge work until the dirty worktree in `graxia os` is stabilized enough to separate pre-existing changes from integration changes.

  ## Repo Provenance

  ### Repo A — `C:\Users\menum\agent-stack`

  - Git provenance: not available.
  - `git branch --show-current` fails with `fatal: not a git repository (or any of the parent directories): .git`.
  - Package root exists with `pnpm` workspace and TypeScript runtime apps.
  - Top-level runtime layout verified:
    - `apps/openclaw-gateway`
    - `apps/hermes-worker`
    - `apps/n8n-orchestrator`
    - `apps/mercury-sidecar`
    - `packages/shared-contracts`
    - `packages/context-pipeline`
    - `packages/knowledge-plane`
  - Docs verified:
    - `docs/ARCHITECTURE.md`
    - `docs/ENTERPRISE_IMPLEMENTATION_PLAN.md`
    - `docs/RUNTIME_RUNBOOK.md`
    - `docs/PRE_IMPLEMENTATION_FULL_SYSTEM_AUDIT.md`
  - Current package scripts verified in `package.json`:
    - `typecheck`
    - `test`
    - `ops:prod-gate`

  ### Repo B — `C:\Users\menum\graxia os`

  - Git provenance: available.
  - Current branch: `staging`.
  - Worktree state: heavily dirty.
  - Current diff volume from `git diff --stat`: `231 files changed, 19730 insertions(+), 11776 deletions(-)`.
  - Recent commit history indicates already-landed waves:
    - `b892187 feat: add local operator UI dashboards`
    - `888804b feat: add safe agent revenue workflows`
    - `93a4c01 feat: add token-efficient context engine MCP tools`
    - `eeee6f5 feat: add mock Google Workspace MCP tools`
    - `df82332 feat: add approval-gated MCP write tools and migration safety`
    - `7d47ae5 feat: add read-only MCP control plane`
    - `e44727d feat: complete revenue funnel delivery email analytics and lead core`
  - Repo layout verified:
    - `backend/`
    - `frontend/`
    - `docs/`
    - `config/`
    - `scripts/`
    - `n8n/`
    - `infrastructure/`
    - `graxia/`
  - High-risk repo hygiene issue: `.venv` and `backend/venv` churn is present in tracked changes.

  ## What Actually Exists

  ### Repo A — `agent-stack`

  - Runtime intake/control plane app exists: `apps/openclaw-gateway`
  - Worker app exists: `apps/hermes-worker`
  - Workflow/orchestration app exists: `apps/n8n-orchestrator`
  - Helper/client app exists: `apps/mercury-sidecar`
  - Shared contract package exists: `packages/shared-contracts`
  - Context package exists: `packages/context-pipeline`
  - Knowledge write-safe package exists: `packages/knowledge-plane`
  - Runtime test harness exists under `tests/`
  - Production gate script exists: `scripts/ci/prod-ready-gate.mjs`

  ### Repo B — `graxia os`

  - Backend route hub is real and broad in `backend/app/api/router.py`.
  - MCP server/control-plane code exists in `backend/app/api/mcp.py` and `backend/app/mcp/registry.py`.
  - Funnel/business backend exists in `backend/app/api/funnel.py`.
  - Approval model exists in `backend/app/models/approval_request.py`.
  - Multi-tenant enforcement exists in `backend/app/models/base.py` via `TenantMixin.organization_id`.
  - Operator UI exists in `frontend/src/App.tsx` with admin routes for:
    - `/admin/agent-control`
    - `/admin/mcp-tools`
    - `/admin/workflows`
    - `/admin/approvals`
    - `/admin/context-packs`
    - `/admin/workspace-exports`
    - `/admin/funnel/analytics`
    - `/admin/audit`
    - `/admin/readiness`
  - Migrations exist under `backend/alembic/versions/`
  - n8n assets exist under `n8n/workflows/`

  ## Verified Evidence

  ### Repo A evidence

  - `C:\Users\menum\agent-stack\package.json`
    - workspace apps/packages layout
    - `pnpm` scripts for runtime validation
  - `C:\Users\menum\agent-stack\scripts\ci\prod-ready-gate.mjs`
    - real readiness gate script exists
    - unhappy-path bug present: `getJson()` and `getText()` push to `failures` without local scope

  ### Repo B evidence

  - `C:\Users\menum\graxia os\backend\app\api\router.py`
    - includes `funnel_router`, `mcp_router`, `approvals_router`, `audit_router`, `health_router`, `orchestration_router`
  - `C:\Users\menum\graxia os\backend\app\mcp\registry.py`
    - registry supports `risk_level`, `required_permission`, `requires_approval`
    - registry blocks dangerous tools at registry layer
    - approval-required tools are expected to create `ApprovalRequest`
  - `C:\Users\menum\graxia os\backend\app\models\approval_request.py`
    - `ApprovalRequest` extends `TenantMixin`
    - has `action_type`, `status`, `policy_class`, `preview`, `expires_at`, `resolved_at`
  - `C:\Users\menum\graxia os\backend\app\models\base.py`
    - `TenantMixin.organization_id` is non-null and indexed
    - `before_insert` guard raises if `organization_id` is missing
  - `C:\Users\menum\graxia os\backend\app\api\funnel.py`
    - funnel/delivery/lead/analytics/recommendation handlers exist
    - recommendation approval flow exists
  - `C:\Users\menum\graxia os\frontend\src\App.tsx`
    - operator/admin UI routes are wired in the main app

  ## Duplicate Systems / Overlap Map

  ### Strong overlap

  - Approval-gated agent actions
  - Workflow orchestration concepts
  - Context/token optimization concepts
  - Audit/readiness/control-plane concepts
  - Runtime-to-business event handling concepts

  ### Repo A stronger today

  - Clean runtime decomposition between gateway, worker, orchestrator, sidecar
  - Typed runtime package boundaries
  - Small, auditable TypeScript surface
  - Runtime idempotency/replay/dead-letter style foundation

  ### Repo B stronger today

  - Business/funnel domain already implemented
  - Backend API already implemented
  - MCP control plane already implemented
  - Operator UI already implemented
  - Approval model and org-scoped backend patterns already implemented
  - Existing migrations/persistence already implemented

  ### Likely duplicate contracts

  - Approval request shape
  - Workflow/task state envelopes
  - Audit event schemas
  - Readiness status/report objects
  - Context packet/tool result envelopes

  ## Conflicting Assumptions

  ### Repo A assumptions

  - Monorepo runtime-first architecture
  - No database-first requirement
  - No existing frontend/operator shell
  - No existing MCP implementation
  - No git provenance

  ### Repo B assumptions

  - FastAPI + React business platform already exists
  - MCP/UI/funnel/workflows are already part of the product surface
  - Database/migrations already exist
  - Git history and existing branch strategy matter
  - Large dirty worktree makes provenance-sensitive merges risky

  ## Missing Systems Relative To Final Target

  ### Still missing or not yet proven globally

  - Clean cross-repo unified contracts
  - Stable selective import path from `agent-stack` into `graxia os`
  - Proven event bridge from Graxia business events into OpenClaw-style runtime dispatch
  - Clean runtime extraction inside `graxia os` for gateway/worker/orchestrator separation
  - Verified global staging/prod gates after merge

  ## Do-Not-Merge-Yet List

  - Do not copy `C:\Users\menum\agent-stack` root over `C:\Users\menum\graxia os`.
  - Do not import `node_modules`, `.test-dist`, `.tmp-runtime-gate`, or generated logs from `agent-stack`.
  - Do not import `.venv`, `backend/venv`, local DB files, backups, or tracked dependency churn from `graxia os`.
  - Do not merge while `graxia os` still has 231-file dirty diff with vendor/runtime artifacts mixed into product changes.
  - Do not create a second MCP stack in parallel to the existing `graxia os` MCP layer.
  - Do not create a second operator UI app unless the existing frontend is explicitly abandoned.
  - Do not create a new root repo while the user has explicitly chosen `C:\Users\menum\graxia os` as the main project.

  ## Hidden Merge Risks

  - Git asymmetry:
    - Repo A has no `.git`
    - Repo B has active branch/history
  - Hygiene risk:
    - `graxia os` currently mixes app changes with `.venv`/vendor churn
  - Architecture duplication risk:
    - importing runtime apps blindly can produce two approval systems, two MCP layers, and two workflow planes
  - Contract drift risk:
    - both repos already express approval/context/workflow concepts differently
  - Regression attribution risk:
    - with the current dirty `graxia os` state, post-merge failures will be hard to attribute

  ## Safe Merge Strategy

  ### Decision

  Use `C:\Users\menum\graxia os` as the canonical integration root.

  ### Why

  - User explicitly chose it as the main project.
  - It already contains the product-facing business system, MCP layer, operator UI, migrations, docs, and git history.
  - `agent-stack` is better treated as a donor runtime architecture, not the merge root.

  ### Strategy

  1. Preserve `graxia os` as the only active git root.
  2. Treat `agent-stack` as an external import source.
  3. Do not merge by folder overlay.
  4. Import only selected runtime assets and concepts from `agent-stack`.
  5. Unify contracts before moving runtime code.
  6. Map imported runtime pieces onto existing Graxia backend/frontend surfaces.

  ### Recommended import mode

  - Primary approach: selective source import with provenance note.
  - Keep an archive snapshot/reference of `agent-stack`, but do not adopt its root layout wholesale.
  - Start by importing concepts/files into clearly named subtrees only after Phase 1 planning is approved.

  ### Recommended target mapping

  - `agent-stack/packages/shared-contracts`
    - source for unified typed envelopes/contracts
  - `agent-stack/apps/openclaw-gateway`
    - source for runtime dispatch/policy/idempotency patterns
  - `agent-stack/apps/hermes-worker`
    - source for worker capability boundaries
  - `agent-stack/apps/n8n-orchestrator`
    - source for workflow dispatch/bus boundaries
  - `agent-stack/apps/mercury-sidecar`
    - optional reference only
  - `agent-stack/packages/context-pipeline`
    - source for correctness-gated context packaging patterns
  - `agent-stack/packages/knowledge-plane`
    - source for safe write-back patterns only

  ### What should stay primary from `graxia os`

  - `backend/app/api/*`
  - `backend/app/models/*`
  - `backend/alembic/*`
  - `frontend/src/*`
  - existing MCP transport and tool surface
  - existing approval data model
  - existing operator UI routes
  - existing funnel/business domain

  ## Proposed Phase 1 Direction

  ### Goal

  Prepare `graxia os` for selective runtime integration without breaking provenance.

  ### First mandatory cleanup boundary

  - Separate product changes from environment/vendor churn in `graxia os`
  - Exclude `.venv` and similar artifacts from merge work
  - Produce a clean changed-files classification before any runtime import

  ### First technical integration step after cleanup

  - Build a contract crosswalk between:
    - existing `graxia os` approval/funnel/MCP schemas
    - `agent-stack` shared runtime envelopes

  ### First runtime import target

  - Shared contract layer only
  - Not gateway app
  - Not worker app
  - Not operator UI

  ## Stop Conditions

  - Stop if `graxia os` dirty state is not stabilized enough to isolate integration edits.
  - Stop if imported runtime code requires replacing the existing MCP/UI stack instead of extending it.
  - Stop if shared contract unification would break existing `graxia os` APIs without a compatibility shim.
  - Stop if any planned import requires reading secret `.env` contents.

  ## Recommendation

  - Approve Phase 1 only if the next task is:
    - merge hygiene + provenance stabilization in `graxia os`
    - changed-files classification
    - shared-contract crosswalk design
  - Do not start code integration from gateway/worker/MCP/UI immediately.

  ## Audit Status

  Audit completed read-only. No implementation changes made.

# Auto-Post into Graxia OS Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate Auto-Post's unique content, social publishing, private YouTube pilot, and video-analysis capabilities into Graxia OS without duplicating auth, database, approvals, API shells, workers, or frontend applications.

**Architecture:** Graxia's existing content engine remains primary. Auto-Post is a donor of missing social queue, publisher adapters, publish-attempt ledger, video-analysis contract, and operational safeguards. Source migrations are rewritten into Graxia's Alembic chain, standalone shims are discarded, and all external publishing remains dry-run/human-approved by default.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy/Alembic, PostgreSQL, Redis/Celery, React/TypeScript, Meta Graph API, YouTube Data API, TikTok Content Posting API, local/social-video analysis worker.

## Global Constraints

- Preserve the dirty `C:/auto-post` worktree through the master-plan source snapshot before integration.
- Never overlay repository roots or copy `backend/main.py`, standalone database/config/auth shims, Docker roots, or frontend shell into Graxia.
- Graxia owns auth, tenant, RBAC, approvals, audit, rate limits, metrics, DB sessions, Celery application, API router, and frontend shell.
- Publishing and ads default to dry-run. Live actions require human approval, provider preflight, idempotency key, and a durable attempt record.
- Public social retrieval never bypasses login, cookies, CAPTCHA, or private access.
- Cloud media/transcript egress remains explicit opt-in and provider state remains evidence-based.

---

### Task 1: Produce a behavior and collision crosswalk

**Files:**
- Create: `docs/consolidation/auto-post-capability-crosswalk.md`
- Create: `docs/consolidation/auto-post-file-disposition.csv`
- Test: `tests/test_auto_post_crosswalk.py`

**Interfaces:**
- Each donor file is classified as `port`, `adapt`, `already-covered`, `archive-reference`, or `reject` with a target path and rationale.

- [ ] **Step 1: Inventory Auto-Post behavior** across content CRUD, queue states, approval, publishers, video analysis, scheduler, health, backup, and UI.
- [ ] **Step 2: Map existing Graxia counterparts** in `backend/app/api/content_engine.py`, `backend/app/services/content_engine_service.py`, `backend/app/models/content_engine.py`, `backend/app/tasks/content_engine_tasks.py`, and existing social agents.
- [ ] **Step 3: Mark collisions** for auth, database, config, main app, Celery app, rate limit, metrics, Docker, and frontend shell as adapt/reject rather than copy.
- [ ] **Step 4: Add a test** requiring every tracked donor source file to have one disposition row and every `port/adapt` row to name an existing or planned target path.
- [ ] **Step 5: Review and commit the crosswalk before code movement.**

### Task 2: Define shared Content Ops contracts

**Files:**
- Create: `backend/app/content_ops/contracts.py`
- Create: `backend/app/contracts/social_video_analysis.schema.json`
- Modify: `backend/app/schemas/content_engine.py`
- Test: `backend/tests/test_content_ops_contracts.py`
- Test: `backend/tests/test_social_video_analysis_contract.py`

**Interfaces:**
- `ContentLifecycle`: `pending`, `processing`, `draft`, `review`, `approved`, `publishing`, `published`, `failed`, `archived`.
- `PublishRequest` includes tenant, content ID, provider, scheduled time, approval ID, idempotency key, and dry-run flag.
- `PublishReceipt` includes attempt ID, provider status, external ID when safe, timestamps, retryability, and redacted error code.

- [ ] **Step 1: Write failing compatibility tests** using redacted Auto-Post fixtures and current Graxia content objects.
- [ ] **Step 2: Implement additive contracts and adapters** without changing existing public fields unnecessarily.
- [ ] **Step 3: Separate editorial approval, evidence approval, and publish authorization.**
- [ ] **Step 4: Validate the JSON Schema and Pydantic models against the same fixtures.**

### Task 3: Port durable social queue and publish attempts

**Files:**
- Create: `backend/app/models/social.py`
- Create: `backend/app/models/publish_attempt.py`
- Create: `backend/alembic/versions/021_content_ops_social_queue.py`
- Create: `backend/alembic/versions/022_content_ops_publish_attempts.py`
- Create: `backend/app/services/publish_attempts.py`
- Test: `backend/tests/test_content_ops_publish_attempts.py`
- Test: `backend/tests/test_content_ops_migrations.py`

**Interfaces:**
- Produces tenant-scoped SocialPost, ReelQueueItem, ApprovalAuditLog, and PublishAttempt models.
- Unique constraints prevent duplicate provider publication and duplicate request dispatch.

- [ ] **Step 1: Write migration/model tests** for tenant scope, idempotency, legal transitions, external-ID uniqueness, and append-only audit behavior.
- [ ] **Step 2: Rebase Auto-Post migrations 0001/0002/0003/0009/0014/0015** into Graxia revisions 021 and 022; do not retain donor revision IDs.
- [ ] **Step 3: Implement atomic claim/transition helpers** so API and worker paths enforce the same state machine.
- [ ] **Step 4: Upgrade empty and existing disposable PostgreSQL databases** and verify schema metadata parity.

### Task 4: Port publisher adapters behind one interface

**Files:**
- Create: `backend/app/content_ops/publishers/base.py`
- Create: `backend/app/content_ops/publishers/facebook.py`
- Create: `backend/app/content_ops/publishers/instagram.py`
- Create: `backend/app/content_ops/publishers/linkedin.py`
- Create: `backend/app/content_ops/publishers/pinterest.py`
- Create: `backend/app/content_ops/publishers/threads.py`
- Create: `backend/app/content_ops/publishers/tiktok.py`
- Create: `backend/app/content_ops/publishers/x.py`
- Create: `backend/app/content_ops/publishers/youtube.py`
- Test: `backend/tests/content_ops/test_publishers.py`

**Interfaces:**
- Every adapter implements `preflight()`, `publish()`, `lookup()`, and `classify_error()` and returns `PublishReceipt`.
- Provider credentials come from Graxia secret/config boundaries and never enter request/receipt models.

- [ ] **Step 1: Write contract tests** for dry-run, missing credentials, rate limit, permanent failure, transient failure, timeout after provider success, and duplicate retry.
- [ ] **Step 2: Port provider logic** from `C:/auto-post/backend/app/social/**` and `backend/app/integrations/youtube.py`, replacing standalone settings/auth with Graxia dependencies.
- [ ] **Step 3: Require explicit `live=True` plus approved request** at both API and task layers.
- [ ] **Step 4: Record request and reconciliation state** before and after every provider call.
- [ ] **Step 5: Run provider tests without network access.**

### Task 5: Integrate APIs and Celery workers

**Files:**
- Create: `backend/app/api/social.py`
- Modify: `backend/app/api/router.py`
- Create: `backend/app/tasks/content_ops.py`
- Modify: `backend/app/tasks/celery_app.py`
- Modify: `backend/app/tasks/queues.py`
- Modify: `backend/app/api/approvals.py`
- Test: `backend/tests/test_content_ops_api.py`
- Test: `backend/tests/test_content_ops_tasks.py`

**Interfaces:**
- API exposes tenant-scoped list/create/approve/reject/schedule/publish/reconcile operations under `/api/v1/content-ops`.
- Celery tasks claim attempts atomically and are replay-safe across worker restart.

- [ ] **Step 1: Add failing tests** for RBAC, tenant isolation, publish-without-approval rejection, duplicate click, broker failure, and worker replay.
- [ ] **Step 2: Adapt Auto-Post routers** to Graxia dependencies and route naming; do not mount a second FastAPI application.
- [ ] **Step 3: Register queues/tasks in Graxia's Celery app** and use existing observability and rate-budget helpers.
- [ ] **Step 4: Add reconciliation tasks** for attempts stuck after an ambiguous provider response.
- [ ] **Step 5: Run focused API/task tests and Graxia regression tests.**

### Task 6: Port video analysis as an isolated capability

**Files:**
- Create: `backend/app/video_analysis/policy.py`
- Create: `backend/app/video_analysis/schemas.py`
- Create: `backend/app/video_analysis/readiness.py`
- Create: `backend/app/video_analysis/worker_client.py`
- Create: `backend/app/models/video_analysis.py`
- Create: `backend/app/models/video_analysis_run.py`
- Create: `backend/app/api/video_analysis.py`
- Create: `backend/app/tasks/video_analysis.py`
- Create: `backend/alembic/versions/023_content_ops_video_analysis.py`
- Test: `backend/tests/video_analysis/**`

**Interfaces:**
- Preserves explicit consent for cloud media and transcript egress, stage-specific evidence coverage, immutable result hashes, leases, and publish blockers.

- [ ] **Step 1: Port the approved Auto-Post contract/policy tests first.**
- [ ] **Step 2: Adapt models and migration to Graxia tenant, audit, and retention contracts.**
- [ ] **Step 3: Use the external Social Video Reader only through the versioned authenticated worker contract.**
- [ ] **Step 4: Keep partial/blocked retrieval truthful and block publishing when required evidence is incomplete.**
- [ ] **Step 5: Run deterministic fixture and no-network benchmark tests.**

### Task 7: Integrate the existing Graxia frontend

**Files:**
- Create: `frontend/src/features/content-ops/api.ts`
- Create: `frontend/src/features/content-ops/ContentQueue.tsx`
- Create: `frontend/src/features/content-ops/PublishAttempts.tsx`
- Create: `frontend/src/features/content-ops/VideoAnalysis.tsx`
- Modify: `frontend/src/App.tsx`
- Test: `frontend/src/features/content-ops/ContentQueue.test.tsx`

**Interfaces:**
- Adds Content Ops views to the existing shell and auth context; no second frontend application.

- [ ] **Step 1: Write tests** for role visibility, tenant filtering, approval controls, blocked publish state, dry-run receipt, and retry/reconcile UI.
- [ ] **Step 2: Port interaction behavior from Auto-Post tabs** while using Graxia design, routing, auth, and API client conventions.
- [ ] **Step 3: Display safe provider readiness and evidence blockers** without exposing tokens or raw provider errors.
- [ ] **Step 4: Run frontend tests, typecheck, and production build.**

### Task 8: Integrate deployment and operations

**Files:**
- Modify: `docker-compose.yml`
- Modify: `render.yaml`
- Modify: `.github/workflows/ci.yml`
- Create: `docs/runbooks/content-ops.md`
- Create: `scripts/content_ops/doctor.py`
- Test: `backend/tests/test_content_ops_deploy_contract.py`

**Interfaces:**
- Produces API/worker/beat health, migration gates, backup/restore inclusion, queue metrics, spend caps, and a safe doctor report.

- [ ] **Step 1: Add deployment contract tests** for required services, health checks, secret references, and queue bindings.
- [ ] **Step 2: Add Content Ops worker and scheduler roles** to existing deployment definitions.
- [ ] **Step 3: Extend backup/restore and observability** to the new tables and queues.
- [ ] **Step 4: Add `doctor.py`** that reports configured/reachable/authenticated/verified separately and never prints credentials.
- [ ] **Step 5: Run the full backend/frontend/migration/deployment verification matrix.**

### Task 9: Prove parity and cut over

**Files:**
- Create: `docs/evidence/content-ops/2026-09-16-parity/manifest.json`
- Create: `docs/evidence/content-ops/2026-09-16-parity/cutover.md`
- Modify: `C:/auto-post/README.md`

**Interfaces:**
- Produces feature parity evidence and a reversible cutover.

- [ ] **Step 1: Run the same redacted fixture corpus** through Auto-Post and Graxia and compare queue, approval, scheduling, receipt, and evidence behavior.
- [ ] **Step 2: Run Graxia dry-run publishing for every configured provider.**
- [ ] **Step 3: Obtain approval for one private/unlisted YouTube canary or one low-risk social canary.**
- [ ] **Step 4: Verify provider receipt, internal attempt, audit, metrics, and reconciliation.**
- [ ] **Step 5: Disable Auto-Post schedules and credentials but retain the repository and deployment for rollback.**
- [ ] **Step 6: Observe the Graxia path for 14 days with no rollback-triggering defect.**
- [ ] **Step 7: Add archive notice and request explicit approval to archive `auto-post`.**

## Exit Criteria

- Graxia contains one content model, approval path, API shell, worker app, and frontend shell.
- Unique Auto-Post capabilities pass compatibility tests in Graxia.
- Migrations upgrade both empty and existing disposable PostgreSQL databases.
- Every external action is dry-run by default, idempotent, approved, audited, and reconcilable.
- A bounded canary proves the live path before the Auto-Post repository is archived.

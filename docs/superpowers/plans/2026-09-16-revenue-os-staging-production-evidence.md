# Revenue OS Staging and Production Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Release Revenue OS from the canonical Graxia OS repository through a repeatable staging-to-production pipeline whose claims are backed by redacted, source-bound evidence.

**Architecture:** Build one immutable Revenue OS image from a reviewed Graxia commit, deploy it to staging with dedicated PostgreSQL/Redis and Stripe test mode, run automated and operator gates, then promote the identical image digest to production. Evidence is generated from structured receipts, never handwritten success claims, and production starts dark behind the money kill switch.

**Tech Stack:** FastAPI, SQLAlchemy/Alembic, PostgreSQL, Redis/Celery, Docker, Render Blueprint, Stripe, Resend, pytest, GitHub Actions.

## Global Constraints

- Canonical source is `C:/Users/menum/graxia os`; the standalone `C:/revenue_os` is a donor only.
- Staging and production use separate databases, Redis namespaces, Stripe modes, webhook secrets, admin keys, and sender configuration.
- Use a real PostgreSQL database in tests and staging. SQLite cannot prove PostgreSQL migrations, constraints, locking, or enum behavior.
- The production artifact digest must equal the staging artifact digest. Rebuilding after staging invalidates the evidence chain.
- Evidence stores only safe presence booleans, hashes, counts, durations, status codes, and redacted object IDs.
- Production migrations, live charges, live emails, and promotion require explicit operator approval.

---

### Task 1: Freeze the release contract and evidence schema

**Files:**
- Create: `docs/evidence/revenue-os/2026-09-16-rc1/evidence.schema.json`
- Create: `docs/evidence/revenue-os/2026-09-16-rc1/manifest.json`
- Create: `docs/evidence/revenue-os/2026-09-16-rc1/go-no-go.md`
- Create: `scripts/revenue_os/evidence.py`
- Test: `tests/test_revenue_os_evidence_schema.py`

**Interfaces:**
- `EvidenceReceipt` fields: `gate`, `source_sha`, `artifact_digest`, `environment`, `started_at`, `finished_at`, `command`, `exit_code`, `assertions`, `safe_ids`, `log_sha256`, `operator`, and `result`.
- `manifest.json` references receipts by relative path and SHA-256 and contains no raw log body.

- [ ] **Step 1: Write failing schema tests** for missing source SHA, mismatched artifact digest, unknown environment, secret-like values, unredacted email/card patterns, and a GO decision with failed required receipts.
- [ ] **Step 2: Run `pytest tests/test_revenue_os_evidence_schema.py -v`** and confirm failure because the schema/writer does not exist.
- [ ] **Step 3: Implement `scripts/revenue_os/evidence.py`** with `write_receipt()`, `hash_file()`, `validate_manifest()`, and secret/PII rejection.
- [ ] **Step 4: Define required gates**: source, build, dependencies, migrations, backup, restore, auth, webhook, checkout, fulfillment, email, workers, observability, performance, rollback, and reconciliation.
- [ ] **Step 5: Run the schema tests and commit** as `feat(evidence): add source-bound Revenue OS release receipts`.

### Task 2: Make configuration fail closed by environment

**Files:**
- Modify: `.env.production.template`
- Modify: `.env.staging`
- Modify: `graxia/services/revenue_os_api/app.py`
- Modify: `graxia/services/revenue_os_api/dependencies.py`
- Modify: `graxia/services/revenue_os_api/routers/system.py`
- Modify: `graxia/packages/revenue_os/services/kill_switch.py`
- Test: `graxia/packages/revenue_os/tests/test_admin_auth.py`
- Test: `backend/tests/test_production_auth_gate.py`
- Test: `backend/tests/test_staging_auth_readiness.py`

**Interfaces:**
- Readiness separates `configured`, `reachable`, and `verified` for PostgreSQL, Redis, Stripe, email, object storage, and workers.
- Non-local environments refuse startup when JWT/admin/webhook signing secrets are missing or weak.
- Money operations remain disabled until an operator resets the kill switch after deployment checks.

- [ ] **Step 1: Add failing tests** for missing/weak admin key, permissive CORS, missing webhook secret, development Stripe key in production, live Stripe key in staging, and disabled dependencies reported as ready.
- [ ] **Step 2: Run the focused auth/readiness tests and record baseline failures.**
- [ ] **Step 3: Add environment validation** using secret presence and safe key-prefix mode checks without logging values.
- [ ] **Step 4: Make `/api/system/readiness` return non-200** when a required dependency is unavailable and include only safe status fields.
- [ ] **Step 5: Add separate liveness** that proves the process is alive without claiming dependency readiness.
- [ ] **Step 6: Run focused tests, then the complete Revenue OS suite.**

### Task 3: Consolidate and validate the Alembic chain

**Files:**
- Modify: `backend/alembic/env.py`
- Modify: `backend/alembic/versions/007_revenue_os_v10_integration.py`
- Modify: `backend/alembic/versions/008_revenue_os_v10_part2.py`
- Modify: `backend/alembic/versions/009_revenue_os_v10_part3.py`
- Modify: `backend/alembic/versions/010_revenue_os_improvements.py`
- Modify: `backend/alembic/versions/012_revenue_os_v12_data_layer.py`
- Create: `backend/alembic/versions/020_revenue_os_consolidation.py`
- Create: `scripts/revenue_os/check_migrations.py`
- Test: `backend/tests/test_migration_018.py`
- Test: `graxia/packages/revenue_os/tests/test_order_idempotency.py`

**Interfaces:**
- Produces one head revision and an additive migration from the current production-compatible head.
- `check_migrations.py` validates single head, upgrade on an empty database, upgrade from the recorded previous head, downgrade policy, and schema invariants.

- [ ] **Step 1: Inventory every standalone Revenue OS schema delta** and map it to an existing Graxia revision or `020_revenue_os_consolidation.py`.
- [ ] **Step 2: Write failing migration-shape tests** for required unique constraints, webhook event idempotency, append-only ledger support, entitlement lookup, and migration head count.
- [ ] **Step 3: Implement only additive/reversible-safe changes** in revision 020; document irreversible data transforms separately.
- [ ] **Step 4: Run empty-database upgrade and previous-head upgrade** against disposable PostgreSQL databases.
- [ ] **Step 5: Compare SQLAlchemy metadata to the migrated schema** and fail on drift.
- [ ] **Step 6: Save migration receipts and commit** as `feat(revenue-os): consolidate production migration chain`.

### Task 4: Build and verify an immutable release artifact

**Files:**
- Modify: `Dockerfile.revenue-os`
- Modify: `docker-compose.revenue-os.yml`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/release.yml`
- Create: `scripts/revenue_os/build_release.ps1`
- Create: `scripts/revenue_os/sbom.ps1`

**Interfaces:**
- Produces a container image labeled with source SHA and locked dependency state.
- Produces image digest, SBOM hash, dependency scan result, and test receipt.

- [ ] **Step 1: Pin the build context and runtime user** and ensure no `.env`, VCS metadata, local database, cache, virtualenv, or test evidence enters the image.
- [ ] **Step 2: Add CI jobs** for secret scan, dependency scan, Python tests, migration checks, image build, image smoke, and evidence schema validation.
- [ ] **Step 3: Build once** from a clean reviewed commit and record source SHA plus image digest.
- [ ] **Step 4: Inspect the image filesystem** for secrets and prohibited files.
- [ ] **Step 5: Generate an SBOM and bind its hash** to the release manifest.
- [ ] **Step 6: Push the immutable digest** to the configured registry without promoting it.

### Task 5: Provision isolated staging

**Files:**
- Modify: `render.yaml`
- Create: `docs/runbooks/revenue-os-staging.md`
- Create: `scripts/revenue_os/staging_preflight.py`
- Test: `tests/test_revenue_os_render_contract.py`

**Interfaces:**
- Produces staging API, worker, beat, PostgreSQL, and Redis resources with a unique environment marker.
- Staging uses Stripe test mode and non-production email recipient allowlisting.

- [ ] **Step 1: Add a Render contract test** that proves staging and production services use distinct DB/Redis/env groups and the same image reference field.
- [ ] **Step 2: Define staging health checks, worker queues, migration one-shot, backup job, and zero public scheduler/publisher side effects.**
- [ ] **Step 3: Store secrets in the platform secret manager** and record presence booleans only.
- [ ] **Step 4: Deploy the immutable image digest to staging** with the money kill switch active.
- [ ] **Step 5: Run staging preflight** and save provider reachability/authentication receipts.

### Task 6: Prove database backup, migration, and restore

**Files:**
- Create: `scripts/revenue_os/backup_db.ps1`
- Create: `scripts/revenue_os/restore_drill.ps1`
- Create: `docs/runbooks/revenue-os-backup-restore.md`
- Test: `tests/test_revenue_os_backup_scripts.py`

**Interfaces:**
- Produces an encrypted backup, checksum, restore into a disposable database, and invariant report.

- [ ] **Step 1: Test scripts for safe target validation** so production cannot be overwritten by a restore drill.
- [ ] **Step 2: Back up staging before migration** and record database server version, migration head, size, and checksum.
- [ ] **Step 3: Apply migrations through the one-shot migration service.**
- [ ] **Step 4: Restore the backup into a new disposable database** and run row-count plus ledger/order/entitlement invariants.
- [ ] **Step 5: Destroy only the verified disposable target** and retain the encrypted backup according to policy.

### Task 7: Execute the staging money-path matrix

**Files:**
- Create: `scripts/revenue_os/staging_money_path.py`
- Create: `graxia/packages/revenue_os/tests/test_ai_factory_fulfillment.py`
- Modify: `graxia/packages/revenue_os/tests/test_e2e_subscription_flow.py`
- Modify: `graxia/packages/revenue_os/tests/test_webhook_fulfillment.py`

**Interfaces:**
- Produces Stripe test checkout/webhook/refund receipts and internal reconciliation.

- [ ] **Step 1: Prove unauthenticated and underprivileged API calls fail.**
- [ ] **Step 2: Create a Stripe test checkout from server-owned catalog data.**
- [ ] **Step 3: Complete test payment and verify webhook signature, event idempotency, order status, ledger, entitlement, and email outbox.**
- [ ] **Step 4: Replay the webhook and assert exact-once internal effects.**
- [ ] **Step 5: Trigger refund and assert reversal ledger plus entitlement state.**
- [ ] **Step 6: Exercise worker restart between event ingest and fulfillment** and prove eventual exactly-once delivery.
- [ ] **Step 7: Save redacted IDs and reconciliation totals in evidence receipts.**

### Task 8: Prove operations and rollback

**Files:**
- Create: `scripts/revenue_os/smoke.py`
- Create: `scripts/revenue_os/rollback_drill.ps1`
- Modify: `docs/runbooks/revenue-os-deploy.md`
- Create: `docs/runbooks/revenue-os-incident.md`

**Interfaces:**
- Produces receipts for readiness, worker heartbeat, queue depth, alert delivery, kill switch, rollback, and post-rollback schema compatibility.

- [ ] **Step 1: Run health/readiness and metrics checks** and verify logs contain correlation IDs but no secret/PII.
- [ ] **Step 2: Stop Redis and a worker in staging** and verify readiness, retries, alerts, and no duplicate side effects.
- [ ] **Step 3: Trigger and reset the money kill switch** and prove checkout/refund/fulfillment guards.
- [ ] **Step 4: Roll back the application image** while keeping the forward-compatible schema; verify core reads and kill switch.
- [ ] **Step 5: Promote the release candidate to staging again** and prove recovery.

### Task 9: Promote dark production and run the live canary

**Files:**
- Finalize: `docs/evidence/revenue-os/2026-09-16-rc1/manifest.json`
- Finalize: `docs/evidence/revenue-os/2026-09-16-rc1/go-no-go.md`
- Create: `docs/evidence/revenue-os/2026-09-16-live-canary/manifest.json`

**Interfaces:**
- Promotes the exact tested image digest and records one authorized live transaction.

- [ ] **Step 1: Require staging GO signatures** from implementer, independent reviewer, and operator.
- [ ] **Step 2: Back up production and verify restore tooling before migration.**
- [ ] **Step 3: Deploy the staging-tested digest to production** with the money kill switch still active.
- [ ] **Step 4: Run production-safe readiness/auth/observability/rollback checks.**
- [ ] **Step 5: Register the Stripe live webhook and send a dashboard test event.**
- [ ] **Step 6: Obtain explicit approval for one real Ai Factory canary payment.**
- [ ] **Step 7: Reset the kill switch only for the bounded canary, complete it, reconcile it, and re-enable the switch if any assertion fails.**
- [ ] **Step 8: Mark production GO only when source SHA, image digest, migration head, Stripe IDs, internal IDs, email delivery, and reconciliation form one complete evidence chain.**

## Exit Criteria

- Canonical Graxia Revenue OS code and schema are the only production source.
- Staging and production receipts refer to the same image digest.
- Backup and restore are executed, not merely documented.
- Auth, webhook, idempotency, failure recovery, rollback, and money kill switch are proven.
- One authorized real charge reconciles exactly and fulfills securely.
- No secret, card data, email address, or raw customer payload appears in committed evidence.

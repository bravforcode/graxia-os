# Graxia Revenue Factory Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put Ai Factory on a real, auditable money path; make Revenue OS staging and production evidence complete; consolidate Auto-Post and the standalone Revenue OS into Graxia OS; then reduce GitHub to a small, intentional portfolio without touching `krisphy` or `adminmate-ai`.

**Architecture:** `graxia-os` becomes the canonical control plane, Revenue OS, approval system, content engine, publisher, evidence ledger, and operations runtime. `ai-factory` remains a thin independently deployed storefront that uses Stripe-hosted checkout and Graxia Revenue OS for webhook processing, entitlement, and digital delivery. `revenue-os` and `auto-post` remain rollback donors until parity and production soak gates pass, then become archived read-only repositories.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy/Alembic, PostgreSQL, Redis/Celery, Stripe Checkout/Payment Links/Webhooks, Resend, Vercel, Render, React/TypeScript/Vite/Bun, GitHub Actions.

## Global Constraints

- Do not modify, archive, transfer, rename, or delete `krisphy` or `adminmate-ai`.
- Never copy `.env`, `.env.bak*`, credentials, OAuth tokens, local databases, virtual environments, Celery schedules, logs, or generated runtime state into another repository or commit.
- Treat the apparent live-key-shaped material previously observed in `ai-factory/STATE.md` as compromised until the Stripe dashboard proves otherwise; rotate/revoke before live launch and remove it from current content without printing it.
- Preserve all dirty worktree changes in `C:/revenue_os`, `C:/auto-post`, and `C:/Users/menum/graxia os`; no reset, stash, checkout-overwrite, or blind folder copy.
- `graxia-os` owns auth, tenant boundaries, database/session setup, approvals, audit, health, metrics, and deployment. Donor shims must not create second versions of those systems.
- Money paths fail closed. Amounts and product identity come from server-side catalog data, webhook signatures are mandatory, event processing is idempotent, and a kill switch guards checkout/refund/fulfillment.
- All outbound publishing, ad spend, bulk email, live payment, production migration, repository archive, and repository deletion require an explicit human gate.
- Production claims require receipts tied to commit SHA, container/build digest, environment, timestamp, and redacted provider identifiers. A README claim or old test count is not evidence.
- Archive is the default cleanup action. Delete only empty/duplicate repositories after a verified bundle backup and a 30-day quarantine.

---

## Target Repository Model

| Repository | Final role | Decision |
|---|---|---|
| `graxia-os` | Canonical application, Revenue OS, Content Ops, workflows, evidence | Keep active |
| `ai-factory` | Static storefront and product marketing only | Keep active |
| `portfolio-production` | Public sales portfolio | Keep active |
| `bravforcode` | GitHub profile and verified case studies | Keep active |
| `thaolai-web` | Separate client delivery system | Keep separate |
| `krisphy` | Protected by user instruction | Do not touch |
| `adminmate-ai` | Protected by user instruction | Do not touch |
| `revenue-os` | Temporary donor/rollback source | Archive after Revenue OS production gate |
| `auto-post` | Temporary donor/rollback source | Archive after Content Ops parity and soak |
| remaining repositories | Portfolio archive, donor import, or deletion candidate | Follow cleanup child plan |

## Dependency Order

```text
Preserve dirty donors and rotate suspected secrets
        |
        +--> Reconcile Revenue OS into graxia-os
        |        |
        |        +--> Staging evidence --> dark production --> real-payment canary
        |                                                |
        |                                                +--> Ai Factory full live rollout
        |
        +--> Selectively port Auto-Post into graxia-os --> content parity canary
                                                         |
                                                         +--> Archive donor repos

Portfolio classification --> archive notices --> 30-day quarantine --> optional deletes
```

### Task 1: Establish immutable preservation points

**Files:**
- Create: `docs/consolidation/source-manifest.json`
- Create: `docs/consolidation/secret-scan-summary.md`
- Modify: `.gitignore`

**Interfaces:**
- Produces a manifest with repository, branch, HEAD, dirty-file classification, bundle checksum, and donor disposition.
- Produces clean preservation branches without committing ignored secrets or runtime artifacts.

- [ ] **Step 1: Record source state** with `git status --porcelain=v2`, `git rev-parse HEAD`, and `git diff --binary` in each donor; write hashes and file classifications to `source-manifest.json`.
- [ ] **Step 2: Extend ignore rules** before preservation so `.env*` except examples, `.venv*`, `node_modules`, `*.db`, `celerybeat-schedule*`, `*.log`, build output, screenshots, and generated trend/content datasets cannot enter snapshot commits.
- [ ] **Step 3: Run secret scanning** against tracked files and all proposed untracked files. Record only rule IDs, file paths, and remediation status in `secret-scan-summary.md`; never copy matched values.
- [ ] **Step 4: Create local preservation branches** named `preserve/revenue-os-20260916` and `preserve/auto-post-20260916`; commit only reviewed source/docs/tests, leaving secrets and runtime artifacts untracked.
- [ ] **Step 5: Create recoverable bundles** outside the repositories and record SHA-256 checksums. Verify each with `git bundle verify` before any consolidation begins.
- [ ] **Step 6: Commit** the manifest and safe ignore changes in Graxia OS as `chore(consolidation): record donor source and safety boundaries`.

### Task 2: Make Graxia OS the canonical Revenue OS source

**Files:**
- Modify: `graxia/packages/revenue_os/**`
- Modify: `graxia/services/revenue_os_api/**`
- Modify: `graxia/packages/revenue_os/tests/**`
- Modify: `Dockerfile.revenue-os`
- Modify: `docker-compose.revenue-os.yml`
- Modify: `render.yaml`
- Create: `docs/consolidation/revenue-os-delta-map.md`

**Interfaces:**
- Consumes the preserved standalone `revenue-os` source SHA.
- Produces one canonical Revenue OS package/API and a parity report showing every donor delta as ported, rejected with rationale, or intentionally deferred.

- [ ] **Step 1: Build a semantic delta map** between `C:/revenue_os` and `graxia/packages/revenue_os` plus `graxia/services/revenue_os_api`; classify model, migration, API, dashboard, security, deployment, and operations changes.
- [ ] **Step 2: Reject donor-only framework shims** when Graxia already owns the concern. Keep Graxia database, identity, auth, API shell, and deployment contracts primary.
- [ ] **Step 3: Port security-critical donor deltas first**: route authentication, webhook signature verification, idempotency, CORS/JWT production checks, backup scripts, and payout reconciliation tests.
- [ ] **Step 4: Rebase schema changes** into the Graxia Alembic chain; never copy standalone migration revision IDs blindly.
- [ ] **Step 5: Run focused parity tests** followed by the complete Revenue OS suite against a real PostgreSQL test database and Redis. Record exact commands and results.
- [ ] **Step 6: Freeze standalone development** with a README notice pointing to Graxia OS and the canonical source SHA; do not archive yet.
- [ ] **Step 7: Commit** the reconciliation in reviewable slices: security, schema, business logic, dashboard, and operations.

### Task 3: Complete Revenue OS staging and production evidence

**Files:**
- Follow: `docs/superpowers/plans/2026-09-16-revenue-os-staging-production-evidence.md`
- Create: `docs/evidence/revenue-os/2026-09-16-rc1/manifest.json`
- Create: `docs/evidence/revenue-os/2026-09-16-rc1/go-no-go.md`

**Interfaces:**
- Produces a staging release candidate and the same immutable artifact promoted to production.
- Produces redacted receipts for migration, backup/restore, auth, checkout, webhook, fulfillment, email, metrics, rollback, and incident controls.

- [ ] **Step 1: Execute the Revenue OS child plan through the staging GO gate.**
- [ ] **Step 2: Deploy the exact staging artifact to production in dark mode** with checkout disabled by the money kill switch.
- [ ] **Step 3: Run production-safe smoke tests** and verify rollback before enabling a live-payment canary.
- [ ] **Step 4: Obtain founder approval** for one bounded real charge and optional immediate refund.
- [ ] **Step 5: Capture the production evidence chain** without card data, customer PII, or secrets.

### Task 4: Put Ai Factory on the verified live money path

**Files:**
- Follow: `docs/superpowers/plans/2026-09-16-ai-factory-live-payments.md`

**Interfaces:**
- Consumes Revenue OS production webhook, entitlement, fulfillment, and evidence endpoints.
- Produces one canary product, then ten verified live products, with secure delivery and rollback.

- [ ] **Step 1: Rotate suspected credentials and remove public-download exposure.**
- [ ] **Step 2: Complete Stripe test-mode checkout, webhook, entitlement, delivery, refund, and replay evidence.**
- [ ] **Step 3: Launch one lowest-risk product as a real-payment canary.**
- [ ] **Step 4: Expand to all products only when canary reconciliation is exact.**
- [ ] **Step 5: Keep paid ads off until organic checkout and fulfillment are reliable and support/refund operations are ready.**

### Task 5: Consolidate Auto-Post into Graxia OS

**Files:**
- Follow: `docs/superpowers/plans/2026-09-16-auto-post-graxia-consolidation.md`

**Interfaces:**
- Consumes the preserved Auto-Post source SHA and Graxia auth/db/approval/runtime contracts.
- Produces one content queue, one approval model, one publisher interface, one video-analysis contract, and one operations surface inside Graxia OS.

- [ ] **Step 1: Complete behavioral inventory and collision map.**
- [ ] **Step 2: Port missing domain features without importing standalone shims.**
- [ ] **Step 3: Rebase migrations, integrate workers, and add compatibility tests.**
- [ ] **Step 4: Run dry-run and private-publish canaries with explicit operator approval.**
- [ ] **Step 5: Hold Auto-Post as rollback source until parity and soak gates pass.**

### Task 6: Archive donor repositories safely

**Files:**
- Modify: `revenue-os/README.md`
- Modify: `auto-post/README.md`
- Create: `docs/consolidation/archive-receipts/revenue-os.json`
- Create: `docs/consolidation/archive-receipts/auto-post.json`

**Interfaces:**
- Produces reversible GitHub archives and local bundles; no source is destroyed.

- [ ] **Step 1: Require 14 consecutive days** with no rollback to either donor and no unresolved Sev-1/Sev-2 defects attributable to consolidation.
- [ ] **Step 2: Tag final donor commits** as `pre-consolidation-2026-09-16` and verify tags are included in bundles.
- [ ] **Step 3: Replace donor READMEs** with archive status, canonical repository link, final source SHA, migration date, and recovery instructions.
- [ ] **Step 4: Disable donor deployments, schedules, webhooks, and write credentials** after verifying Graxia equivalents.
- [ ] **Step 5: Archive `revenue-os` and `auto-post` on GitHub** only after explicit user confirmation; record archive timestamps and URLs.

### Task 7: Clean the remaining GitHub portfolio

**Files:**
- Follow: `docs/superpowers/plans/2026-09-16-github-repository-cleanup.md`
- Create: `docs/repository-inventory.yaml`

**Interfaces:**
- Produces an explicit keep/import/archive/delete classification for every owned repository.

- [ ] **Step 1: Re-fetch repository state immediately before action** because issue, PR, deployment, and visibility state may have changed.
- [ ] **Step 2: Apply archive notices and disable broken automations before archiving.**
- [ ] **Step 3: Archive in small batches and verify links, Releases, Pages, and bundles after each batch.**
- [ ] **Step 4: Quarantine deletion candidates for 30 days.**
- [ ] **Step 5: Delete only with a second explicit confirmation listing exact repository names.**

## Release Gates

| Gate | Required evidence | Blocks |
|---|---|---|
| G0 Preservation | bundles verify, source manifest, clean secret scan disposition | any merge/import |
| G1 Revenue parity | standalone-vs-Graxia delta map closed, tests green | staging |
| G2 Staging GO | migrations, backup/restore, auth negative tests, Stripe test flow, rollback | production deploy |
| G3 Production dark GO | readiness, metrics, logs, rollback, kill switch | real charge |
| G4 Money canary GO | charge, signed webhook, idempotent order, entitlement, delivery, reconciliation | all products |
| G5 Content parity GO | API/model/worker/UI compatibility and dry-run receipts | live publishing |
| G6 Archive GO | 14-day soak, no rollback, final bundles/tags/readmes | donor archive |
| G7 Delete GO | 30-day quarantine and second explicit approval | repository deletion |

## Self-Review

- Scope coverage: live payments, Revenue OS staging/production evidence, Auto-Post integration, repository consolidation, and protected repositories are each assigned a child plan and a measurable gate.
- Safety coverage: dirty worktrees, suspected secret exposure, payment/webhook idempotency, secure delivery, rollback, and reversible archive are explicit blockers.
- Architecture consistency: Graxia OS is the only control plane; Ai Factory is a storefront; donor repositories are temporary recovery sources.
- No production, payment, publishing, archive, or delete action is authorized by this document alone.

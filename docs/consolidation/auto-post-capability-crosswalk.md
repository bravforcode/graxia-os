# Auto-Post → Graxia OS capability crosswalk

Status: `PUBLISHER_CONTRACT_PORTED — DURABLE_STORE_PORTED — ADAPTER_RUNTIME_PENDING`

Source snapshot: `C:/auto-post` at the preservation point recorded in
`docs/consolidation/source-manifest.json`. The donor worktree is dirty; this
crosswalk therefore names behavior and target boundaries without copying files.

## Canonical ownership

Graxia OS remains the only owner of identity, tenant isolation, RBAC, approval
records, audit logs, rate limits, metrics, database sessions, Celery app,
FastAPI router registration, and the existing frontend shell. Auto-Post is a
donor for unique content-operations behavior only.

| Capability | Graxia target | Default | Cutover gate |
|---|---|---|---|
| Content lifecycle | `backend/app/content_ops/contracts.py` + existing content engine | local DB only | contract tests |
| Social queue | planned `backend/app/models/social.py` | no provider call | migration + tenant tests |
| Publish attempts | `backend/app/content_ops/publisher.py` + `backend/app/content_ops/durable_store.py` + `PublishAttempt` model | dry-run | idempotency + reconcile tests |
| Provider adapters | `PublisherAdapter` contract in `backend/app/content_ops/publisher.py` | missing credential blocks | no-network adapter tests |
| Video analysis | planned `backend/app/video_analysis/` | cloud egress off | consent + hash + lease tests |
| API/worker integration | planned Graxia router and Celery tasks | approval required | RBAC + replay tests |
| Frontend | planned `frontend/src/features/content-ops/` | display only | role/tenant UI tests |

## Collision rules

- Never copy Auto-Post `backend/main.py`, database/config/auth modules,
  Docker roots, or frontend shell into Graxia.
- A provider call requires `dry_run=false`, an approved request, consent, an
  idempotency key, a durable attempt store injected by production wiring, and an
  operator gate. The new contract defaults to dry-run and rejects raw provider
  errors/tokens. The in-memory store is test/local-only; production wiring can
  inject the SQLAlchemy async store after the API/worker approval path is
  connected.
- Public video retrieval cannot bypass login, cookies, CAPTCHA, or private
  access. Cloud media/transcript egress remains explicit consent.
- Donor migrations are references only. Any Graxia migration gets a new
  revision in Graxia's chain after schema review; donor revision IDs are not
  reused.
- `auto-post` remains a rollback donor until parity, canary, and a 14-day soak
  pass. No archive action is authorized by this file.

## Review scope

`auto-post-file-disposition.csv` covers the runtime files that can change money,
publishing, tenant state, or external media. Documentation, generated datasets,
local artifacts, and standalone deployment roots remain archive-reference by
default and require a separate file-level decision before import.

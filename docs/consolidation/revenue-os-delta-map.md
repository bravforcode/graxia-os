# Revenue OS donor → Graxia OS delta map

Status: `DELTA_MAP_READY — PARITY_EXECUTION_PENDING`

This is a structural reconciliation map, not a production-readiness claim.
No donor file was copied and no migration, deploy, payment, webhook, or archive
operation was performed.

## Source evidence

| Field | Value |
|---|---|
| Donor | `C:/revenue_os` |
| Donor source SHA | `39eb5116e38cbba19db577d945218edb369ffe3f` |
| Donor branch | `master` |
| Donor dirty entries at preservation | `46` |
| Graxia baseline SHA | `b490c37a6f6ead1dab6373771244a788c19be4d0` |
| Graxia integration branch | `codex/revenue-factory-20260916` |
| Structural donor file count | `420` tracked files |
| Structural Graxia Revenue OS file count | `198` files |
| Shared leaf-name signal | `156` names; not parity evidence |

The donor contains sensitive-looking environment backups and a large dirty
surface. Only reviewed source/docs/tests may be considered for import.

## Delta decisions

| Domain | Donor surface | Canonical Graxia surface | Decision | Required proof |
|---|---|---|---|---|
| Identity, auth, tenant | `api/auth.py`, `services/auth_service.py`, tenant helpers | Graxia auth middleware, dependencies, org scope | `reject` duplicate shims | negative auth and tenant-isolation tests |
| API shell | `api/main.py`, donor routers | `graxia/services/revenue_os_api/app.py` and routers | `adapt` only missing routes | OpenAPI and auth contract diff |
| Checkout and webhook | donor checkout/webhook routes and `services/webhook_processor.py` | `routers/checkout.py`, `routers/orders.py`, `services/webhook_processor.py` | `adapt` security-critical deltas | signature, price, idempotency, replay tests |
| Fulfillment and email | donor `services/fulfillment_service.py`, `email_service.py`, worker tasks | Graxia fulfillment/email services and `celery/tasks/digital_fulfillment.py` | `adapt` missing behavior | private delivery, retry, refund/revoke tests |
| Ledger, refunds, payout | donor order/refund/payout services and tests | Graxia order, refund, finance, and ledger modules | `port/adapt` tests first | reconciliation totals and append-only ledger invariants |
| Kill switch and operations | donor kill switch, incident, outbox, monitoring | Graxia kill switch, incidents, outbox, readiness | `already-covered` then close gaps | kill-switch drill, queue health, rollback receipt |
| SEA marketplace expansion | donor `api/sea`, `services/sea`, and SEA worker tasks | no Ai Factory acceptance target | `defer` | separate product decision and scope gate |
| Schema and migrations | donor Alembic revisions `002`–`007` plus dirty revisions | Graxia Alembic chain | `reject` donor IDs; rewrite only | upgrade empty/disposable DB and migration-head receipt |
| Deployment | donor Docker/Compose/Railway files | Graxia Dockerfile, Render staging/production resources | `adapt` operational deltas | same image digest across staging and production |
| Worker runtime | donor `worker/` and Celery entrypoint | Graxia Celery app and queues | `reject` second app; port task logic | replay-safe task tests and worker restart drill |

## Closure rule

The donor is not archive-ready until every `adapt` row has a target commit and
focused test receipt, every `defer` row has an owner decision, and the staging
and production evidence manifest references the same source/artifact chain.

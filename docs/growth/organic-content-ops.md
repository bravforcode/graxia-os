# Organic content batch operations

The weekly batch is deliberately dry-run only until a provider adapter, account
consent, credentials, and a current human approval are present.

## Schedule

Celery beat runs `tasks.organic_content_batch.schedule_weekly` every Monday at
08:00 in the configured worker timezone. The task creates at most one batch per
ISO week and queues work; it never performs AI generation in the request path.

Set these production environment values on the worker before enabling it:

```text
CONTENT_BATCH_ENABLED=true
ORGANIC_CONTENT_WEEKLY_ENABLED=true
ORGANIC_CONTENT_WEEKLY_ORGANIZATION_ID=<public-organization-uuid>
ORGANIC_CONTENT_WEEKLY_TOPIC=<weekly-topic>
ORGANIC_CONTENT_WEEKLY_CANONICAL_URL=https://bravforcode.github.io/graxia/
ORGANIC_CONTENT_WEEKLY_SITE=site_a
ORGANIC_CONTENT_WEEKLY_LANGUAGE=th
```

The scheduler creates nine items: one pillar article, three supporting/FAQ
pages, and five platform-specific short-form variants. The worker keeps the
batch queued if the broker is unavailable so an operator can replay it safely.

## Publishing boundary

The default result is an export/dry-run. Live publishing requires, per item:

- unexpired human approval;
- provider in the allowlist;
- provider account consent that is not revoked;
- credentials available in production secrets;
- claim, canonical, UTM, and idempotency checks passing; and
- a successful canary receipt.

A missing provider or consent is a blocked publish, not a successful publish.
Never label an exported or dry-run item as published.

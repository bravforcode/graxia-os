# Ai Factory Live Payments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accept real THB payments for Ai Factory products with signed webhook processing, secure fulfillment, reconciliation, support, and rollback evidence.

**Architecture:** Keep the storefront static on Vercel and use Stripe-hosted Payment Links/Checkout. Stripe sends signed events to Graxia Revenue OS, which creates idempotent orders and entitlements, sends delivery email containing an expiring private download URL, and records evidence. Product assets must not be served from the public Vercel deployment.

**Tech Stack:** Static HTML, Vercel, Stripe Payment Links/Checkout/Webhooks, PromptPay where enabled for the Stripe account, Graxia Revenue OS, private object storage, Resend.

## Global Constraints

- Rotate/revoke any credential that may have appeared in repository content before live mode.
- Never store Stripe secret keys or webhook signing secrets in GitHub, HTML, JSON catalogs, logs, evidence files, or Vercel client variables.
- Public JSON may contain Payment Link URLs because they are customer-facing; it must not contain secret keys.
- Product amount, currency, and fulfillment asset mapping are controlled by the Revenue OS catalog, not query parameters or browser input.
- Do not expose paid files under `downloads/` or any other public static path.
- The first live run is one explicitly approved canary charge. Do not enable all products or ad traffic first.

---

### Task 1: Close credential and public-asset exposure

**Files:**
- Modify: `STATE.md`
- Modify: `.gitignore`
- Modify: `.vercelignore`
- Modify: `SECURITY.md`
- Modify: `downloads/**`
- Create: `security/secret-remediation-2026-09-16.md`
- Test: `test-url-patterns.ps1`

**Interfaces:**
- Produces a repository that contains no live secret and deploys no paid asset publicly.

- [ ] **Step 1: Run a history-aware secret scan** and list only affected file paths and commit IDs.
- [ ] **Step 2: In Stripe Dashboard, revoke/rotate any matching or uncertain key** and record the dashboard rotation timestamp plus key fingerprint suffix only.
- [ ] **Step 3: Remove secret-shaped material from current files.** If history contains a confirmed live secret, prepare a separate `git filter-repo` plan and request destructive-history approval before execution.
- [ ] **Step 4: Move product files to private object storage** and exclude `downloads/**` from Vercel output. Store object keys in the server-side Revenue OS catalog.
- [ ] **Step 5: Add a deployed URL test** proving direct requests to every former asset path return 404/403 and do not redirect to a public object.
- [ ] **Step 6: Commit** as `security(ai-factory): rotate credentials and privatize paid assets`.

### Task 2: Define one canonical product/payment catalog

**Files:**
- Modify: `products.json`
- Modify: `stripe-links.json`
- Generate: `stripe-links-live.json`
- Modify: `check-prices.py`
- Modify: `verify-stripe.py`
- Test: `test-all-stripe.py`

**Interfaces:**
- `products.json` owns `slug`, display name, `amount_satang`, `currency`, active state, and Revenue OS product ID.
- Revenue OS owns `stripe_product_id`, `stripe_price_id`, fulfillment object key, and entitlement policy.
- `stripe-links-live.json` maps slug to public Payment Link URL only and is generated from verified dashboard/API output.

- [ ] **Step 1: Add catalog validation** for unique slug, positive integer satang amount, `THB`, exact ten-product coverage, and no duplicate Revenue OS/Stripe identifiers.
- [ ] **Step 2: Seed or reconcile the ten catalog rows in Revenue OS** using idempotent upsert by slug.
- [ ] **Step 3: Create Stripe live Products/Prices** from the reviewed catalog with stable slug metadata; do not infer live IDs from test IDs.
- [ ] **Step 4: Create one Payment Link per active product** with billing/receipt settings and success URL pointing to the corresponding thanks page.
- [ ] **Step 5: Enable eligible payment methods in Stripe.** PromptPay requires THB and account eligibility; record configured/available/used as separate evidence states.
- [ ] **Step 6: Run catalog and Stripe read-only verification** and fail on amount, currency, mode, redirect, or metadata mismatch.
- [ ] **Step 7: Commit** public catalog/link changes without secrets.

### Task 3: Wire Stripe events to Revenue OS fulfillment

**Files:**
- Modify: `graxia/services/revenue_os_api/routers/checkout.py`
- Modify: `graxia/packages/revenue_os/services/webhook_processor.py`
- Modify: `graxia/packages/revenue_os/services/fulfillment_service.py`
- Modify: `graxia/packages/revenue_os/services/email_service.py`
- Modify: `graxia/packages/revenue_os/celery/tasks/digital_fulfillment.py`
- Create: `graxia/packages/revenue_os/services/signed_download_service.py`
- Test: `graxia/packages/revenue_os/tests/test_ai_factory_fulfillment.py`
- Test: `graxia/packages/revenue_os/tests/test_webhook_fulfillment.py`

**Interfaces:**
- Consumes signed Stripe `checkout.session.completed`, refund, and payment-failure events.
- Produces one idempotent Order, append-only ledger entries, one Entitlement, one delivery outbox item, and an expiring signed URL.

- [ ] **Step 1: Write failing tests** for valid payment, duplicate event replay, wrong amount, unknown Price ID, invalid signature, delivery retry, expired link, refund revocation, and partial refund policy.
- [ ] **Step 2: Verify tests fail at the missing secure-delivery boundary.**
- [ ] **Step 3: Implement server-side Price ID lookup** and reject events whose amount/currency/product do not match the catalog.
- [ ] **Step 4: Make event ingestion idempotent** by Stripe event ID and checkout session/payment intent ID; persist the provider IDs needed for reconciliation.
- [ ] **Step 5: Create entitlement and outbox records in the same database transaction** as the paid-order transition.
- [ ] **Step 6: Generate short-lived signed URLs on demand** from private object keys; never persist a permanent public link.
- [ ] **Step 7: Deliver via existing email outbox** with retry and a deterministic email idempotency key.
- [ ] **Step 8: Process refund events** by append-only ledger mutation and entitlement revocation according to policy.
- [ ] **Step 9: Run focused and full Revenue OS tests.**

### Task 4: Make thanks pages truthful and non-sensitive

**Files:**
- Modify: `thanks-01-prompt-pack-th.html`
- Modify: `thanks-02-obsidian-student-kit.html`
- Modify: `thanks-03-freelance-pricing-calculator.html`
- Modify: `thanks-04-cold-email-template-pack.html`
- Modify: `thanks-05-ai-automation-workflow.html`
- Modify: `thanks-06-cv-international-template.html`
- Modify: `thanks-07-n8n-sme-workflow-pack.html`
- Modify: `thanks-08-content-calendar-90d.html`
- Modify: `thanks-09-finance-tracker-thb.html`
- Modify: `thanks-10-ai-agent-starter-github.html`
- Modify: `_thanks_template.html`
- Test: `test-deployed.ps1`

**Interfaces:**
- Pages confirm that payment is processing/complete and direct the buyer to email/support.
- Pages never treat query-string values as proof of payment and never expose a paid asset.

- [ ] **Step 1: Add tests** proving pages contain no direct paid-asset URL, secret, or claim that browser redirect alone confirms payment.
- [ ] **Step 2: Replace direct-download UI** with delivery status, support route, expected email behavior, and retry-safe instructions.
- [ ] **Step 3: Preserve accessibility, mobile layout, and Thai/English copy.**
- [ ] **Step 4: Deploy to a Vercel preview and run all page/link checks.**

### Task 5: Complete test-mode evidence

**Files:**
- Modify: `test-stripe-e2e.py`
- Modify: `test-deployed.ps1`
- Create: `evidence/test-mode/manifest.json`
- Create: `evidence/test-mode/reconciliation.json`

**Interfaces:**
- Produces a redacted end-to-end receipt tied to exact Ai Factory and Graxia commit SHAs.

- [ ] **Step 1: Execute one Stripe test checkout** from a deployed preview.
- [ ] **Step 2: Verify signed webhook acceptance and invalid-signature rejection.**
- [ ] **Step 3: Replay the same event and prove no duplicate order, entitlement, ledger entry, or email is created.**
- [ ] **Step 4: Verify delivery email and one-time/expiring download behavior.**
- [ ] **Step 5: Execute refund and prove ledger/entitlement state reconciles.**
- [ ] **Step 6: Record commit SHAs, artifact digest, Stripe test object IDs, internal IDs, timestamps, and assertions with PII redacted.**

### Task 6: Run one live canary and expand safely

**Files:**
- Modify: `LAUNCH-CHECKLIST.md`
- Modify: `STATE.md`
- Create: `evidence/live-canary/manifest.json`
- Create: `evidence/live-canary/go-no-go.md`

**Interfaces:**
- Produces verified proof that money reached Stripe and fulfillment/reconciliation completed.

- [ ] **Step 1: Confirm production kill switch, alerting, support inbox, refund procedure, and rollback owner.**
- [ ] **Step 2: Enable only the selected lowest-risk product Payment Link.** Keep the other nine links unpublished.
- [ ] **Step 3: Obtain explicit founder approval for one real charge.**
- [ ] **Step 4: Complete the purchase and verify charge, webhook, order, ledger, entitlement, delivery, and download separately.**
- [ ] **Step 5: Reconcile Stripe gross/net/fee values against Revenue OS and optionally execute a refund to verify reversal.**
- [ ] **Step 6: Record a GO only if every identifier joins one-to-one and no secret/PII appears in logs or evidence.**
- [ ] **Step 7: Publish the remaining nine verified links in two batches, checking reconciliation after each batch.**
- [ ] **Step 8: Keep paid ads disabled until at least five organic/internal transactions complete without fulfillment or reconciliation defects; this is an operating gate, not a revenue promise.**

## Exit Criteria

- All ten live links match the reviewed THB catalog.
- Public deployment contains no paid asset and no secret.
- Invalid webhooks fail; valid and repeated webhooks are idempotent.
- A live canary proves charge, order, ledger, entitlement, delivery, support, and rollback.
- Stripe and Revenue OS reconcile exactly for the canary.
- The live release can be disabled by deactivating Payment Links and triggering the Revenue OS money kill switch.

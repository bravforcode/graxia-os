# Autonomous Ecommerce — Design (2026-08-16)

**Status**: Approved by user (16 Aug 2026)
**Owner**: Graxia OS / Revenue OS
**Vision**: 100% autonomous ecommerce — agents run the store end-to-end with policy engine as the only guardrail (no human approval), full audit trail, kill switch.

---

## 1. Requirements (collected)

| Aspect | Decision |
|--------|----------|
| Products | Digital + Physical (POD/dropship) |
| Channels | Own store (Phase 1) → Shopify (P2) → Shopee/Lazada/TikTok (P3) → Amazon (P3) |
| Autonomy | **Full autonomous 100%** — no human approval. Policy engine + audit + kill switch replace approval workflow |
| Marketing | Organic first (P1), paid ads (Meta/Google/TikTok) in P2 |
| Start | Digital-first on own store |

**Key existing assets (reuse, no rewrite):**
- 33 models (`graxia/packages/revenue_os/models.py`): Order, Product, Refund, Entitlement, LedgerEntry, Lead, RevenueCampaign, Approval, EmailOutbox, DeliveryEvent, AutomationLock/Run, IncidentEvent, WebhookEvent, AuditLog, StrategyLog, MetricDaily, RevenueExperiment, ContentIdea/Post, AIDraft, BWCPMessage, AttributionEvent/Summary, CampaignBudgetSnapshot
- Full commerce enums (`enums.py`): order/delivery/refund/campaign/lead statuses, IncidentSeverity, AgentType, BWCPMessageType
- Stripe webhook flow: `checkout.py` (HMAC), `webhook_processor.py` (checkout.session.completed, invoice.paid, payment_failed, refund), idempotent `order_service.create_order_from_payment`
- Payment platforms: stripe | gumroad | paypal | manual
- Celery infra: `celery/celery_app.py` + tasks (campaign_engine, daily_revenue_ops, hourly_monitor, weekly_review, send_pending_emails, process_outbox, agent_consumers)
- Services: order, refund, fulfillment, email (Resend + EmailOutbox), campaign, approval, outbox, webhook_processor, bwcp, scoring
- Agents: VisionaryAgent, SalesAgent (draft_outreach_email), ChiefOfStaffAgent (escalate_issue), event_handlers
- HITL infra to be **repurposed**: Approval model/service → replaced by policy engine for full autonomy
- Automation: AutomationLock (distributed lock), AutomationRun, automation router (list_locks, force_release_lock, trigger_task, get_schedule)
- Observability: AuditLog, StrategyLog, IncidentEvent, WebhookEvent, MetricDaily
- Frontend: storefront exists — `frontend/src/pages/StorePage.tsx`, `StoreProductPage.tsx`, `lib/api.ts`, `hooks/use-revenue-os.ts`, `components/ui/` (36 components)

---

## 2. Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │           STOREFRONT (frontend React)       │
                    │   catalog → checkout(Stripe) → chat widget  │
                    └──────────────┬──────────────┬───────────────┘
                                   │              │
                    ┌──────────────▼──────────────▼───────────────┐
                    │            REVENUE OS API (FastAPI)          │
                    │  checkout/orders/refunds + support, policy,  │
                    │  autonomy routers (new)                      │
                    └──────┬───────────────────────────┬──────────┘
                           │                           │
              ┌────────────▼───────────┐   ┌───────────▼───────────┐
              │   POLICY ENGINE (new)  │   │  SERVICE LAYER (have) │
              │  hard-constraint rules │◄──│  order/email/refund/  │
              │  allow = proceed       │   │  fulfillment/outbox   │
              │  deny = incident+log  │   └───────────┬───────────┘
              └────────────▲───────────┘               │
                           │                           │
              ┌────────────┴──────────────────────────▼┐
              │         CELERY + REDIS (have)          │
              │  agent_consumers | hourly_monitor |    │
              │  send_pending_emails | daily_ops |     │
              │  digital_fulfillment (new)             │
              └───────────────────────────────────────┘
                           │
              ┌────────────▼──────────────────────────┐
              │     AGENT LAYER (extend existing)     │
              │  commerce_ops (new) ← main decision   │
              │  support_agent (new) ← customer chat  │
              │  sales/visionary/chief_of_staff (have)│
              └───────────────────────────────────────┘
```

**Core principle**: Every money/product-touching action (price change, discount, refund, order status, campaign pause) MUST pass policy engine first. Policy engine replaces `approval_service` as the decision gate — human approval becomes machine policy check.

---

## 3. New Components

### 3.1 Policy Engine

**Model** `PolicyRule` (add to `models.py`):
- `id` UUID PK, `action: str` (PRICE_CHANGE, DISCOUNT, REFUND, FULFILL, CAMPAIGN_PAUSE, CAMPAIGN_PUBLISH, EMAIL_SEND, CONTENT_PUBLISH, AD_BUDGET, PURCHASE), `rule_type: str` (min|max|allow|deny), `value: float`, `scope: str` (global|product_type|product_id), `enabled: bool`, `priority: int`, `created_at`, `updated_at`

**Engine** `PolicyEngine.check(action, context) → PolicyDecision(allow, reason)`:
- Loads all enabled rules matching scope; highest priority wins on conflict
- Any deny → deny
- Fail-closed: if engine error or no rules configured for action → **deny** (never allow silently)
- Deny path: `AuditLog` entry + `IncidentEvent` (severity: LOW for routine denies, MEDIUM+ if money at stake) + action not executed

**Default seed rules** (Phase 1):
- DISCOUNT max 15% (global)
- PRICE_CHANGE max ±20% per change, min 1 hour between changes per product
- REFUND allow ≤ 100% only for orders < 30 days old
- CAMPAIGN_PAUSE allow; CAMPAIGN_PUBLISH allow only if content approved by copywriter quality check
- FULFILL allow only for PAID orders
- EMAIL_SEND allow ≤ 5 per customer per day

**Admin-only API** for rules — agents CANNOT modify rules (this is the single wall in a full-autonomous system).

### 3.2 Digital Fulfillment

Flow: Stripe webhook → `order_service` (idempotent, Order=PAID + LedgerEntry CHARGE) → celery task `digital_fulfillment`:
1. Generate delivery token (UUID, expires 7 days, max 5 downloads)
2. Send email with download link via `EmailOutbox` → `email_service` (Resend)
3. Mark `DeliveryEvent` DELIVERED
4. Grant `Entitlement` (existing model) for the product
5. Idempotent: re-runs on duplicate webhook do nothing (existing dedupe pattern)

### 3.3 Commerce Ops Agent

Main store manager, runs on celery beat (extend `hourly_monitor` / `daily_revenue_ops` cadence):
1. **Read state**: orders (24h), products, campaigns, metrics, leads, incidents
2. **Decide**: LLM + rules → propose action (e.g., "product X sales down 3 days → lower price 10%")
3. **Policy check** → if allow: execute via service layer + `StrategyLog` + `AuditLog`; if deny: log + incident
4. **Write daily report** (extend `daily_revenue_ops`)

**Phase 1 jobs** (organic):
- Price optimization (within ±20% policy)
- Discount engine (abandon cart, win-back coupons ≤15%)
- Campaign lifecycle: draft → publish → monitor → pause on KPI miss
- Content factory: research → `copywriter` draft → publish (blog/social/email)
- Lead nurture: score → `sales.draft_outreach_email` → follow-up
- Refund triage: analyze request → auto-refund per policy / escalate
- Support chat (3.4)
- Escalation via `chief_of_staff.escalate_issue`

**Phase 2 jobs** (add): dynamic pricing (rule-based), ad management (Meta/Google/TikTok — AD_BUDGET policy), POD/dropship sourcing & restock (supplier API + PURCHASE policy)

**Phase 3 jobs** (add): KOL/affiliate program (AFFILIATE policy)

### 3.4 Support Agent

Router `POST /api/support/chat`:
1. Classify intent: WISMO | REFUND | PRODUCT_QUESTION | COMPLAINT | SALES
2. Can do: order status answer, policy-checked refund initiation, catalog product Q&A, product recommendation, lead capture (SALES intent → `Lead` + `sales.py`)
3. Cannot do: payment disputes → `IncidentEvent` + "escalated to team" reply
4. Frontend: floating chat widget (new component)

### 3.5 Kill Switch + Observability

- `autonomy_enabled` flag (DB) + router `autonomy.py` (GET status / POST enable-disable)
- Every agent action checks flag first; disabled → agents stop immediately (store keeps selling, just unmanaged)
- Existing `AutomationLock` as distributed lock preventing duplicate agent runs
- `AuditLog` on every action: agent, action, policy result, before/after state

---

## 4. Data Flow — 100% Autonomous Loop (digital order example)

1. Customer buys via Stripe Checkout (existing storefront + checkout router)
2. Stripe webhook → `order_service` (idempotent) → Order=PAID + LedgerEntry CHARGE
3. Celery `digital_fulfillment` → token → email with link → Entitlement + DeliveryEvent DELIVERED
4. Support agent handles WISMO/refund (policy-checked) immediately
5. Nightly: `commerce_ops` reads metrics → decides (price/campaign/content) → policy check → execute → StrategyLog+AuditLog
6. Emergency: kill switch off → agents stop, store keeps running

---

## 5. Error Handling & Safety

- **Policy deny** = only stop condition for agents; every deny → IncidentEvent + AuditLog (never silent)
- **Idempotency**: every webhook/task deduped (existing pattern) — no double email/refund
- **Payment failure**: no fulfillment + dunning email (stub exists in webhook_processor)
- **LLM error/timeout**: fail-safe = do nothing + log (never guess)
- **Distributed locks**: no duplicate agent runs
- **Backtest before enable**: replay historical MetricDaily → simulate agent decisions → measure outcome (RevenueExperiment + MetricDaily)
- **Chaos testing**: existing `testing/chaos_engine.py` — test kill switch + policy fail-closed

---

## 6. File Map (paths)

### Backend — package (`graxia/packages/revenue_os/`)

| File | Action | Purpose |
|------|--------|---------|
| `models.py` | MODIFY | Add `PolicyRule` (Section 3.1) |
| `enums.py` | MODIFY | Add `ActionType`, `RuleType`, `SupportIntent` enums |
| `schemas.py` | MODIFY | Add PolicyRule schemas, SupportChat schemas, PolicyDecision |
| `core/policy_engine.py` | **NEW** | `PolicyEngine.check(action, context) → PolicyDecision`, rule loading, fail-closed |
| `services/digital_fulfillment.py` | **NEW** | Delivery token gen, entitlement grant, email trigger (idempotent) |
| `agents/commerce_ops.py` | **NEW** | Main decision loop: read state → decide → policy-check → execute → log |
| `agents/support.py` | **NEW** | Intent classification + policy-checked actions + escalation |
| `celery/tasks/digital_fulfillment.py` | **NEW** | Celery task wrapping digital_fulfillment service |
| `celery/tasks/agent_consumers.py` | MODIFY | Wire commerce_ops loop cadence |
| `celery/tasks/daily_revenue_ops.py` | MODIFY | Add agent daily report + price/discount jobs |
| `core/copywriter.py` | MODIFY (minor) | Quality gate hook for CAMPAIGN_PUBLISH/CONTENT_PUBLISH |
| `tests/test_policy_engine.py` | **NEW** | Rule matrix tests, fail-closed tests |
| `tests/test_digital_fulfillment.py` | **NEW** | Idempotency, token expiry, entitlement grant |
| `tests/test_support_agent.py` | **NEW** | Intent classification, policy-checked refund, escalation |
| `tests/test_commerce_ops.py` | **NEW** | Decision→action mapping, policy deny behavior |

### Backend — API (`graxia/services/revenue_os_api/routers/`)

| File | Action | Purpose |
|------|--------|---------|
| `support.py` | **NEW** | `POST /api/support/chat` → support agent |
| `policy.py` | **NEW** | Admin-only rule CRUD (agents cannot modify) |
| `autonomy.py` | **NEW** | Kill switch: GET/POST `autonomy_enabled` |
| `checkout.py` | MODIFY | Trigger digital_fulfillment task on PAID (or via celery signal) |
| `__init__.py` / `router.py` | MODIFY | Register new routers |

### Frontend (`frontend/src/`)

| File | Action | Purpose |
|------|--------|---------|
| `components/chat/SupportChat.tsx` | **NEW** | Floating support chat widget (uses `lib/api.ts`) |
| `pages/StorePage.tsx` | MODIFY (minor) | Mount chat widget; digital product "instant delivery" hint |
| `pages/StoreProductPage.tsx` | MODIFY (minor) | Digital asset display, buy flow already via Stripe |
| `lib/api.ts` | MODIFY | Add `support.chat()`, `autonomy.status()`, `policy.*` client calls |
| `hooks/use-revenue-os.ts` | MODIFY | Expose support/autonomy hooks |

---

## 7. Testing Strategy

- **Unit**: policy engine (rule matrix, fail-closed), digital fulfillment (idempotency), support intent classifier, commerce_ops decision→action mapping
- **Integration**: Stripe webhook → order → fulfill → email chain (extends existing 12 test files)
- **Chaos**: kill switch, policy fail-closed (existing chaos_engine)
- **Backtest harness**: replay MetricDaily → simulate agent → measure (new `tests/test_backtest_harness.py` in P2)

---

## 8. Roadmap

| Phase | Scope | Est. |
|-------|-------|------|
| **P1 (4 wk)** | Digital own-store: policy engine + digital fulfillment + commerce_ops (organic jobs) + support agent + kill switch + tests | 4 wk |
| **P2 (4 wk)** | Shopify connector + ads (Meta/Google/TikTok) + POD/dropship + dynamic pricing + backtest harness | 4 wk |
| **P3** | Shopee/Lazada/TikTok Shop + Amazon + affiliate/KOL | — |

---

## 9. Open Questions / Notes

- Payments already wired (Stripe/PayPal/Gumroad) — no new gateway work
- Approval/BWCP infra stays (audit value) but is bypassed for autonomous actions
- Digital asset storage location (S3/local/CDN) to be decided at implementation — token points to storage key
- POD supplier choice (Printful/Printify) deferred to P2

---

## 10. Phase 1 Status (2026-08-16)

**Tasks 1–9 implemented and committed on `review/rydc-atr-pnl-honesty`.**

### Completed
- **Task 1** Policy engine: fail-closed dual PERCENT+ABSOLUTE caps, `AutonomyMode` (off/shadow/limited/full), circuit breaker (5 MEDIUM+ incidents/60 min → auto-OFF + HIGH incident). 12 tests.
- **Task 1a** Admin auth pinned: reused existing `require_admin_api_key` (`ADMIN_API_KEY`, constant-time, `X-Admin-Api-Key`/Bearer). 4 tests.
- **Task 2** `/api/autonomy/status` + `/api/autonomy/mode` (router-level auth). HTTP-verified: 401 no key, 403 wrong key, 422 bad mode. 3 tests.
- **Task 3** `/api/policy/rules` CRUD + `/api/policy/seed` (dual-cap aware schemas). 4 tests.
- **Task 4** Digital fulfillment wired: Stripe/Gumroad/PayPal webhooks create PAID orders and fulfill immediately (idempotent); locked 5-min sweep task catches missed orders. 5 tests. `OrderStatus.PAID` added (additive).
- **Task 5** Commerce ops agent: price-cut job (policy-gated, `value_cents` included), campaign pause (budget `should_pause`), stale-order escalation, daily StrategyLog; SHADOW mode logs-only; circuit breaker blocks cycle. 7 tests.
- **Task 6** Support agent: one-time 6-digit verification code (emailed, hashed, 15 min TTL, 5-attempt burn), WISMO gated, refunds idempotent + per-customer capped + 30-day window + dual-cap + escalate-above-cap, complaints escalate. 10 tests. `SupportVerification` model.
- **Task 6a** Stripe refund executor: PROCESSING → PROCESSED (with `platform_refund_id`) / FAILED; non-Stripe skipped; idempotent. 3 tests.
- **Task 7** `POST /api/support/chat` (public, identity verified in agent). 1 test.
- **Task 8** Celery beat: digital-fulfillment (5 min), process-refunds (5 min), commerce-ops (hourly) — all lock-wrapped; overlap test. 1 test.
- **Task 9** Frontend `SupportChat` widget (floating, verification-code input flow) mounted on StorePage; `supportChat` API client. 2 tests.

### Test infra unblocked (pre-existing breakage fixed, needed to run any test)
- `conftest.py`: removed dead `_get_or_init_database_url` import; clean-slate per-test fixture (services commit internally); session `loop_scope` via pytest-asyncio 1.4.0; tolerant teardown (pre-existing FK cycle in drop_all).
- `models.py`: `bwcp_messages.incident_id` FK pointed at non-existent table; `Order.idempotency_key` got a client-side default (NOT NULL without default broke direct construction).
- API boot: `schemas/` dir renamed `schemas_pkg/` (shadowed by `schemas.py` module); `checkout.py` imported non-existent `order_service`; `db.py` exposes `DATABASE_URL`; `middleware.py` starlette `headers.pop` compat.
- `fulfillment_service.fulfill_order`: idempotency via `DeliveryEvent` existence (removed reference to non-existent `Order.delivery_status`).
- `webhook_processor.py`: rewritten against current schema (`amount_cents`, `product_id`, customer stats; previously referenced obsolete `total_amount`/`delivery_status`/`total_orders`/`total_spent`).
- `chief_of_staff.escalate_issue` is a module-level function (not a class method) — callers updated.
- Venv repair: `pydantic-core==2.46.4` (mismatch with pydantic 2.13.4); `pytest-asyncio>=0.24` (loop management).

### Migration (manual DDL — alembic chain requires pgvector; not applicable to this DB)
For a fresh deployment, create the new tables (or rely on `Base.metadata.create_all`):

```sql
CREATE TABLE IF NOT EXISTS revenue_os_policy_rules (
    id UUID PRIMARY KEY,
    action VARCHAR(50) NOT NULL,
    rule_type VARCHAR(20) NOT NULL,
    value DOUBLE PRECISION,
    value_type VARCHAR(20) NOT NULL DEFAULT 'percent',
    limited_multiplier DOUBLE PRECISION NOT NULL DEFAULT 0.25,
    scope VARCHAR(50) NOT NULL DEFAULT 'global',
    scope_value VARCHAR(255),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    priority INTEGER NOT NULL DEFAULT 100,
    description VARCHAR(500),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_policy_action_scope ON revenue_os_policy_rules (action, scope);

CREATE TABLE IF NOT EXISTS revenue_os_autonomy_state (
    id INTEGER PRIMARY KEY,
    mode VARCHAR(20) NOT NULL DEFAULT 'off',
    updated_at TIMESTAMPTZ DEFAULT now()
);
-- If an earlier deployment had `enabled` column: map enabled=false -> mode='off', enabled=true -> mode='full' explicitly.

CREATE TABLE IF NOT EXISTS revenue_os_support_verifications (
    id UUID PRIMARY KEY,
    email VARCHAR(320) NOT NULL,
    code_hash VARCHAR(64) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_support_verification_email ON revenue_os_support_verifications (email);

-- OrderStatus gained 'paid' (Postgres enum type 'orderstatus'): ALTER TYPE orderstatus ADD VALUE IF NOT EXISTS 'paid';
```

### Baseline (pre-existing) failures — NOT caused by Phase 1, documented for the record
- Backend `graxia/packages/revenue_os/tests/`: 14 pre-existing failures — copywriter signature drift (5), fulfillment entitlement tests (3), celery task assert drift (3), validators rule drift (1), approval draft (1), campaign metrics (1). 123 passed.
- Frontend `frontend/tests/`: 3 pre-existing failures (NoticeBanner role query etc.). 40 passed.

---

## 11. Phase 2 Status (2026-08-16)

**Plan:** `docs/superpowers/plans/2026-08-16-autonomous-ecommerce-phase2-plan.md` — 9 tasks.

### Completed (all on `main`)
- **T1 Channel framework**: `ChannelType`/`SupplierStatus` enums; `ChannelConnection`, `SupplierOrder` (unique idempotency_key), `AdCampaignSync` (unique per platform+campaign), `PriceChangeLock` models; `ChannelAdapter` ABC. 4 tests.
- **T2 Shopify connector**: HMAC webhook verification (before parse), rate-limit-aware client (429 backoff), idempotent order import → PAID → fulfill, reconcile with no-downgrade rule. 5 tests.
- **T3 POD supplier**: policy-gated submission (margin ≥ 20% / cost ≤ 100k THB cents), unique idempotency_key prevents double orders, HMAC status webhooks, locked poll task; `fulfill_order` physical branch (no download link). 3 tests.
- **T4 Meta ads client**: campaigns/metrics/budget/status via Graph API, `sync_ads_metrics` upsert (never budgets). 3 tests.
- **T5 Ads agent job**: ROAS rules (pause <1.0, cut toward target, clamp ±10%), dual-capped via `AD_BUDGET` policy, SHADOW never calls Meta API. 3 tests.
- **T6 Dynamic pricing**: rule signals (stale −10% / hot +5%), shared policy-gated price-write path with 24h `PriceChangeLock`; wired into commerce cycle. 5 tests.
- **T7 Backtest harness**: replays history through the REAL `PolicyEngine.check` in-memory; ESTIMATE impact labels; nightly StrategyLog. 3 tests.
- **T8 Celery beat**: shopify-sync (5 min), supplier-poll (15 min), ads-sync (hourly), backtest-runner (nightly) — all lock-wrapped; task registry updated. Suite: **154 passed, 14 pre-existing failures, 0 errors**.
- **T9 Runbooks**: `docs/runbooks/channel-onboarding.md`, `docs/runbooks/ads-budgets.md`.

### Phase 2 env vars (secrets manager)
`SHOPIFY_STORE_DOMAIN`, `SHOPIFY_ACCESS_TOKEN`, `SHOPIFY_WEBHOOK_SECRET`, `SUPPLIER_API_URL`, `SUPPLIER_API_KEY`, `SUPPLIER_WEBHOOK_SECRET`, `META_ACCESS_TOKEN`, `META_AD_ACCOUNT_ID` — none committed, fail-closed in production.

### Provisioning status
- Phase 1 SHADOW live on local prod-equivalent DB (`graxia-prod-db`, port 5435, `graxia_os`).
- Supabase (root `.env`) unreachable (project paused — DNS fails) — unpause, then run `scripts/provision_autonomy_phase1.py` with that DATABASE_URL (idempotent).
- `STRIPE_SECRET_KEY` in `.env` is still the test placeholder — replace before real money.

## 12. Phase 3 Status (2026-08-16)

**Plan:** `docs/superpowers/plans/2026-08-16-autonomous-ecommerce-phase3-plan.md` — 9 tasks.

### Completed (all on `main`)
- **T1 Platform auth + FX caps**: `PlatformSignedClient`/`BaseSignedClient` (429-aware), `ShopeeSigner`/`LazadaSigner` known-vector signature tests (Shopee v2 `SHA256(key+timestamp+path+partner_id+token)`; Lazada HMAC over sorted key-value), `AmazonTokenCache` (LWA), `ChannelType` += SHOPEE/LAZADA/TIKTOK_SHOP/AMAZON/FX, `AffiliateStatus`, `Affiliate`/`AffiliatePayout`/`ChannelInventory` models, `ActionType.AFFILIATE`; FX-aware ABSOLUTE caps (non-THB converts via `fx_rate`, no-rate → PERCENT-only, fail-closed). 8 tests.
- **T2 Shopee adapter**: shared `import_channel_orders(db, platform, orders)` extracted to `channels/base.py` (shopify wrapper keeps behavior); poll-first `/order/get_order_list` (READY_TO_SHIP), sandbox gate fail-closed in production, status map, reconcile no-downgrade, webhook fails closed (poll-only trigger). 12 tests + shopify suite green.
- **T3 Lazada adapter**: `/orders/get` poll, `user_id` signed via shared client, `/order/pack` + `/order/ship` fulfillment, status map, poll-only trigger. 11 tests.
- **T4 TikTok Shop adapter**: `TikTokSigner`/`TikTokClient` (v202309 formula cross-verified against the EcomPHP SDK; hand-computed GET/POST-body vectors), `POST /api/order/search` poll, `/fulfillment/ship`. 13 tests.
- **T5 Amazon SP-API adapter**: `AmazonSigV4Signer` (verified against botocore reference SDK), `AmazonTokenCache.assume_role` (STS WebIdentityToken, cached), throttle-aware 429 (honors `x-amzn-RateLimit-Limit`), 401 token refresh, PII-safe (ids-only metadata + logs), MFN-only filter. 13 tests.
- **T6 Marketplace sync**: `inventory_reconcile` (available = stock − buffer, never negative), `price_sync` (shared price path + FX-aware caps + 24h lock), `margin_after_fee` wired into the SUPPLIER_PURCHASE gate (per-channel fee_rate, defaults shopee .07/lazada .06/tiktok .08/amazon .15), `fx_refresh` (daily rates → `ChannelConnection(channel="fx")`). 9 tests.
- **T7 Affiliate program**: policy-gated `create_affiliate` (rejects > 20% cap, fail-closed), `record_attribution` (ACTIVE + 30-day window via AttributionEvent, payout = amount × commission, ≥ 50,000 THB → `needs_review` + IncidentEvent MEDIUM, no double payouts), `review_payouts` daily sweep + Telegram (manual payouts for Phase 3); `POST /api/affiliate/create` + `GET /api/affiliate/overview` (admin). 12 tests.
- **T8 Celery beat**: marketplace-poll (10 min), inventory-sync (15 min), fx-refresh (daily), affiliate-review (daily) — all lock-wrapped; task registry updated; import smoke OK. Suite: **233 passed, 14 pre-existing failures, 0 errors** (baseline was 163 passed — +70 new tests, zero new failures).
- **T9 Runbooks**: `docs/runbooks/marketplace-onboarding.md`, `docs/runbooks/affiliate-program.md`.

### Phase 3 env vars (secrets manager)
`SHOPEE_PARTNER_ID`, `SHOPEE_PARTNER_KEY`, `SHOPEE_SHOP_ID`, `SHOPEE_ACCESS_TOKEN`, `LAZADA_APP_KEY`, `LAZADA_APP_SECRET`, `LAZADA_SELLER_ID`, `TIKTOK_SHOP_APP_KEY`, `TIKTOK_SHOP_APP_SECRET`, `TIKTOK_SHOP_SHOP_ID`, `TIKTOK_SHOP_ACCESS_TOKEN`, `AMAZON_LWA_CLIENT_ID`, `AMAZON_LWA_CLIENT_SECRET`, `AMAZON_SP_API_ROLE_ARN`, `AMAZON_SELLER_ID`, `FX_SOURCE_URL` (optional) — none committed, fail-closed in production.

### Phase 3 deploy notes
- New enum values (`ChannelType` + FX, `AffiliateStatus`, `ActionType.AFFILIATE`) require `ALTER TYPE` on already-deployed DBs (`channeltype`, `affiliate_status`, `actiontype`) before the new tables/rows are written.
- New tables: `revenue_os_affiliates`, `revenue_os_affiliate_payouts`, `revenue_os_channel_inventory` (created automatically by `create_all` on fresh DBs; migration path needed for existing deployments).
- All marketplace channels are poll-first — webhook endpoints (where added later) must call `trigger_*_poll` and never import payloads directly.

### Post-Phase-3 expansion (2026-08-16, same day)
- **Listing sync**: real `sync_products` per adapter (add/update by persisted `ChannelInventory.listing_id`); Amazon SKU-mapped PATCH only; per-channel `price_multiplier`.
- **Webhook-trigger endpoints**: `POST /api/channels/{platform}/webhook` (payload never read) + admin `POST /api/channels/{channel}/poll?since=` (backfill).
- **Payout reconciliation**: settlements → append-only FEE/PAYOUT ledger entries (idempotent per ref); `payout-recon` hourly beat; `PayoutProvider` seam.
- **Refund automation**: `RETURNED` reconcile books Refund + negative REFUND ledger entry (HR-16), marketplace executes the money.
- **Competitor repricing**: >5%-above reaction, 2%-undercut target, ±20% clamp, shared price path; `repricing` hourly beat; provider seam.
- **Channel health**: stale `last_sync_at` (>12h) → IncidentEvent LOW once; hourly beat.
- **Delivery SLA**: PAID > 7 days without delivery → IncidentEvent MEDIUM once; daily beat.
- **Affiliate fraud signals**: self-referral + stacking detection on overview.
- **Dashboards**: `/api/dashboard/channels` (per-channel P&L), `/api/dashboard/treasury` (multi-currency with FX), `/api/dashboard/customer/{email}` (cross-platform identity).
- **Migration runner**: `scripts/migrate_revenue_os_phase3.py` — idempotent ALTER TYPE + create_all.
- **Provisioning (EXECUTED on prod-equivalent)**: `scripts/provision_marketplace_channels.py` — all 4 marketplace rows + fx row live on `graxia-prod-db` (sandbox mode); migration runner executed (enum member-name values, model registration fix).
- **Ops toolkit**: `core/rate_budget.py` (token bucket per platform), `channels/tracking_ingest.py` (carrier tracking data path), `agents/channel_ops.py` (per-channel mode-gated cycle), `core/policy_sim.py` (what-if, pure read), `scripts/sandbox_smoke.py` (real sandbox calls, live-guarded).
- Deferred (external dependency): carrier label APIs, affiliate auto-payout money APIs, BI warehouse export, ML demand forecasting, KOL discovery research, platform tax reports.

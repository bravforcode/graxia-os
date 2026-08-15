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

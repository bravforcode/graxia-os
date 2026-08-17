# Graxia Pricing Strategy (P2-12)

**Date:** 2026-08-17 · **Status:** Proposed — needs founder sign-off before seed/checkout changes
**Sources:** [deep-research-synthesis](/docs/research/2026-08-17-deep-research-synthesis.md) + [part2](/docs/research/2026-08-17-deep-research-synthesis-part2.md)

## 1. Problem: current price points don't match the market we can win

Current seed data (`scripts/seed_revenue_os_demo.py`) and the legacy funnel use:

| Tier | Price | Notes |
|---|---|---|
| Lead magnet | ฿0 | 30-page guide |
| Auto-fulfillment (one-time) | ฿990 | LOW_TICKET digital |
| Revenue OS Standard | ฿4,900 | CORE |
| Revenue OS Enterprise | ฿19,900 | CORE |
| Consulting audit | ฿25,000 | SERVICE |

Research says Thai SMEs actually pay **฿250–1,800/month/tool**:

| Benchmark | Price | Conf |
|---|---|---|
| FlowAccount (accounting, syncs Shopee/Lazada/TikTok) | ฿165–457/mo | H |
| Peak (marketplace accounting) | ฿5,000–35,000/yr (≈฿420–2,900/mo) | H |
| LINE OA | ฿1,280–1,780/mo | M |
| Make / Zapier | $9–19.99/mo | H |

**Inference:** ฿4,900–19,900/mo is **10–40× above** what a typical Thai SME
pays for a single tool. Only mid-market (฿1–10M+/yr revenue) justifies it — and
those buyers expect ERP-grade connectors + human support, which we partially have
(FlowAccount/Peak both adding AI/MCP connectors as competitors move).

## 2. Strategic choice: anchor to revenue uplift, not seats/tools

Two viable models:

1. **% of revenue uplift** — we only get paid when we demonstrably grow the
   merchant's revenue. Best alignment, removes price objection, but needs
   revenue tracking (we already have orders + campaigns + attribution in
   Revenue OS) and a payment mechanism (subscription billing exists — P2-10).
2. **Flat SaaS tiers** — simpler, matches how Thai SMEs budget, but must land
   in the ฿250–1,800 range to win the SMB segment the funnel already targets.

**Recommendation: hybrid.** Keep a low-cost SaaS floor for SMB, add a
revenue-share or uplift bonus for mid-market. This mirrors how the market
actually pays (ERP %-fees on marketplace GMV; FlowAccount flat fee for SMB).

## 3. Proposed tier structure

| Tier | Price | Who | What they get |
|---|---|---|---|
| **Starter** | ฿499/mo (or ฿4,900/yr) | SMB <฿1M/yr | 1 channel, orders, fulfillment, basic email, 1 user. Fits ฿250–1,800 band. |
| **Growth** | ฿1,490/mo | SMB ฿1–5M/yr | All channels, campaigns, approvals, AI ops agent (policy-capped), 5 users. |
| **Scale** | ฿4,900/mo | Mid-market ฿5–20M/yr | Everything + SLA 99.5% + onboarding + premium support. |
| **Enterprise / % uplift** | custom, e.g. 5% of attributed uplift (cap ฿49,900/mo) | ฿20M+/yr | Full stack, dedicated ops, SLA 99.9%. |

Rationale vs evidence:
- Starter/Growth land **inside** the observed ฿250–1,800 SMB band (FlowAccount
  457, LINE OA 1,280–1,780) → price objection gone.
- Scale keeps the current ฿4,900 anchor but is repositioned for mid-market.
- % uplift is optional upside that matches "we only win when you win" and
  converts the earlier 4,900–19,900 skepticism into a value story.

## 4. What this means for the funnel (money path = legacy Vercel)

The legacy funnel is the real money path today (Vercel Hobby = free, Stripe
Checkout live, bridge → Revenue OS). Two concrete changes:

1. **One-time products stay one-time** (฿990 auto-fulfillment, ฿25,000 audit).
   No change needed — they're already at market rates.
2. **Subscriptions get the new tiers.** Revenue OS already has
   `Subscription(plan, price_cents)` + Stripe subscription webhook (P2-10) +
   billing portal. Implementing this is a **seed/config change**, not new
   architecture:
   - Update tier constants in seed + a `PLANS` config map
   - Map `plan` → Stripe Price ID (requires Stripe dashboard entries)
   - Legacy funnel checkout for subscriptions must call `create_checkout_session`
     with `mode="subscription"` — Revenue OS `POST /api/checkout/session`
     currently hardcodes `mode="payment"` (checkout.py) → **needs a small
     extension** to support subscription mode.

## 5. Decision needed before implementing

- [ ] Confirm hybrid tier structure (numbers above are proposals)
- [ ] Choose Go-to-market: launch Starter first (fits market, low friction) vs all tiers
- [ ] For % uplift: define attribution rule (Revenue OS has orders + campaigns;
      uplift = revenue in campaign window vs baseline)
- [ ] Stripe dashboard: create Price IDs for new tiers before wiring

## 6. Follow-up code changes (when approved)

- `scripts/seed_revenue_os_demo.py` — new PLAN tiers
- `graxia/services/revenue_os_api/routers/checkout.py` — support `mode="subscription"` in `/api/checkout/session`
- `graxia/packages/revenue_os/services/billing_service.py` — plan mapping to Stripe prices
- Legacy funnel checkout — subscription product wiring

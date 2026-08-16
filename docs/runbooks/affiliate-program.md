# Affiliate / KOL Program Runbook (Phase 3)

Policy-gated affiliate commissions with attribution tracking and manual payout
review. No money moves without a confirmed sale and a human-approved payout.

## Caps (seeded `AFFILIATE` policy rules)

| Rule | Cap |
|---|---|
| PERCENT MAX | 20% commission |
| ABSOLUTE MAX | 2,000,000 THB cents (20,000 THB) per payout |

`POST /api/affiliate/create` (admin key) rejects any commission above the
PERCENT cap (HTTP 422). If the AFFILIATE rules are deleted, creation fails
closed — re-seed before onboarding anyone.

## Attribution

- 30-day attribution window (`ATTRIBUTION_WINDOW_DAYS=30`): the order must be
  purchased within 30 days of the affiliate's first touch
  (`AttributionEvent` with `source=<affiliate code>` + `order_id`).
- `record_attribution` creates a **pending** `AffiliatePayout`:
  `amount = order.amount_cents × commission_percent`.
- Idempotent: one payout per (affiliate, order) — re-runs return `false`.
- Attribution requires an ACTIVE affiliate, an existing order, and a recorded
  touch. Inactive/paused/banned codes, unknown orders, and out-of-window
  orders are silently skipped (no payout, no incident).

## Payout review (manual for Phase 3)

- Threshold: **50,000 THB** (`AFFILIATE_REVIEW_THRESHOLD_CENTS = 5,000,000`).
- Attribution at/above the threshold immediately sets `needs_review=true` and
  raises an IncidentEvent MEDIUM (`source=affiliate`).
- The daily `affiliate-review` beat job re-flags any pending row at/above the
  threshold that was missed and sends a Telegram summary.
- Operator flow: review the order (confirmed sale? no self-referral?) →
  `AffiliatePayout.status`: `pending → approved` (manual DB/operator action for
  Phase 3; no auto-pay).

## Fraud signals (check before approving)

- **Self-referral**: affiliate's own email/device placed the order; same
  customer as the affiliate account.
- **Commission stacking**: multiple affiliates claiming the same order — one
  payout per order by construction, but verify only one touch exists.
- **Fake clicks**: touch with no order in 30 days; mass touches from one IP.
- **Threshold gaming**: orders just under the review threshold from the same
  affiliate — flag manually.

## Kill switch

Autonomy kill switch (see `docs/runbooks/autonomy-rollout.md`) stops all
autonomous actions; affiliate payouts are already manual, so the kill switch
blocks nothing here — but the AFFILIATE policy rules can be tightened at
`/api/policy/rules` (admin) at any time, and affiliate status can be set to
`paused`/`banned` to stop new attributions immediately.

## Overview endpoint

`GET /api/affiliate/overview` (admin key) → total/active affiliates, pending
payouts (count + total cents), rows needing review, `fraud_flags` count.

## Fraud signals (live detection)

`affiliate/service.py: fraud_signals()` runs on every overview call:

- **Self-referral**: payout whose order's customer email equals the affiliate's
  email → flagged `self_referral`.
- **Stacking**: an order with attribution events from 2+ distinct sources →
  flagged `stacking` (one payout per order by construction, but multiple
  touches are suspicious).

Review flagged payouts before approving; the manual checklist above still
applies.

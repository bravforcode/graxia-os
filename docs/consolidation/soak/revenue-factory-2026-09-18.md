# Revenue Factory Soak Gate

Start: 2026-09-18 (Asia/Bangkok)
Canonical source: `C:/Users/menum/graxia os`
Production: `https://graxia-os-funnel.vercel.app`
Branch: `codex/cleanup-evidence-20260917`

This tracker prevents repository archive/delete work from outrunning the
production money path. It records readiness; it does not authorize a charge,
archive, delete, or external publish.

## Owner-approved scope override

On 2026-09-18 the owner instructed the operator to skip the real-payment
exercise and continue the remaining closeout work. The checkout path is
therefore treated as operational for planning and handoff only. This is not a
Stripe charge receipt and does not change the factual readback in
`docs/evidence/revenue-os/2026-09-18-production-504-fix/report.json`.

- [x] Real-payment execution waived by owner for this closeout.
- [x] Staging payment exercise waived by owner for this closeout.
- [x] Production runtime/API evidence retained independently of the waiver.
- [ ] Fourteen-day production soak remains a calendar gate.

## Passed

- [x] Production landing and health returned HTTP 200.
- [x] Live Stripe checkout smoke created a `livemode` session and expired it
      without a charge.
- [x] Live Stripe webhook endpoint is enabled; expired-session event delivered.
- [x] Stripe MCP OAuth reauthorized for the Live `Ai factory` account.
- [x] Funnel-specific local suite passed: 20 tests, 2 warnings.
- [x] Production 504 fix re-deployed and re-verified: health, product, checkout,
      and hosted Checkout page returned HTTP 200.
- [x] AI Factory checkout branch merged into default `master` via PR #4;
      merge commit `c1d027f9482173cd74673aa5dffd13ff06cf1cfd`.

## Required before donor archive

- [~] Staging preflight — waived by owner for this closeout; not represented as
      a passed staging receipt.
- [~] Staging manifest — waived by owner for this closeout; not represented as
      a passed staging receipt.
- [~] Authorized paid-order/fulfillment proof — waived by owner for this
      closeout; no charge, delivery, email, refund, or replay receipt is claimed.
- [x] Production public checkout endpoint returned a Checkout URL without a
      gateway timeout during the production smoke.
- [ ] Fourteen calendar days of production soak have no unresolved critical
      payment or fulfillment incident.
- [ ] Private recovery bundles and refreshed GitHub inventory are verified.

## Repository policy during soak

- Keep `graxia-os` active as the canonical control plane.
- Freeze `revenue-os`, `auto-post`, `enterprise-agent-os`, and `OBS-rag` as
  donors; import only reviewed capabilities.
- Do not modify `krisphy` or `adminmate-ai`.
- Do not archive or delete any repository until every required gate above is
  checked and the exact batch is explicitly approved.

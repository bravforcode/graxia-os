# Revenue Factory Soak Gate

Start: 2026-09-18 (Asia/Bangkok)
Canonical source: `C:/Users/menum/graxia os`
Production: `https://graxia-os-funnel.vercel.app`
Branch: `codex/cleanup-evidence-20260917`

This tracker prevents repository archive/delete work from outrunning the
production money path. It records readiness; it does not authorize a charge,
archive, delete, or external publish.

## Passed

- [x] Production landing and health returned HTTP 200.
- [x] Live Stripe checkout smoke created a `livemode` session and expired it
      without a charge.
- [x] Live Stripe webhook endpoint is enabled; expired-session event delivered.
- [x] Stripe MCP OAuth reauthorized for the Live `Ai factory` account.
- [x] Funnel-specific local suite passed: 20 tests, 2 warnings.

## Required before donor archive

- [ ] Staging preflight passes with test-mode Stripe keys and both kill-switches.
- [ ] Staging manifest is `go` with receipts bound to one source/artifact.
- [ ] One authorized paid-order/fulfillment proof exists, including delivery,
      email, entitlement, refund, and duplicate-webhook behavior.
- [ ] Production public checkout endpoint returns a Checkout URL without a
      gateway timeout during the paid-proof attempt.
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

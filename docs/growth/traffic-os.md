# Traffic OS — Graxia

## Objective

Grow qualified, consented traffic from real users. Synthetic traffic, bot
inflation, unsolicited spam, and load against third-party systems are out of
scope.

## Acquisition loop

```text
Demand research
  -> SEO brief + claim review
  -> human approval batch
  -> pillar page + localized/supporting pages
  -> platform-specific short-form adaptations
  -> lead magnet / product CTA
  -> attribution + consent
  -> referral/share loop
  -> analytics review and next brief
```

## Existing Graxia building blocks

- SEO clusters, product catalog, lead magnets, sitemap, and JSON-LD.
- `ContentEngine` approval queue and `content_ops` dry-run gate.
- First/last-touch attribution, consent evidence, event dedupe, and
  attribution reporting.
- Free public host: `https://bravforcode.github.io/graxia/`.
- No owned custom domain exists yet; do not publish `graxia.store`.
- Static host/API boundary remains explicit: no live checkout or revenue claim
  is made from the GitHub Pages artifact alone.

## Capacity rules

- Public HTML, assets, sitemap, and robots use CDN/browser caching.
- Public product reads may use `s-maxage=300` with stale revalidation.
- Checkout, lead capture, delivery tokens, analytics writes, and health are
  never publicly cached.
- Redis-backed rate limits remain enabled; cache must not bypass consent or
  purchase controls.
- Load testing runs only against an owned staging target with a fixed budget,
  ramp, stop condition, and no provider side effects.

## Growth sequence

1. Build three intent clusters around AI workflows, freelancer pricing, and
   SME automation; publish one pillar and three supporting pages weekly.
2. Produce five channel-native adaptations weekly; require approval, claims
   review, UTM/link checks, and idempotency before publishing.
3. Add measurable share/referral links to delivery and lead-magnet success
   states; suppress marketing when consent is absent.
4. Review source-to-lead and source-to-purchase attribution weekly; expand
   only clusters with evidence of qualified engagement.
5. Run staging load tests before increasing publishing or traffic budgets.

## Acceptance gates

- Organic traffic is real and attributable; no unsupported traffic claims.
- Every marketing message has consent evidence and unsubscribe suppression.
- Every public post has approval, claim review, provider allowlist, canary, and
  idempotency evidence.
- P95 public-page latency and error rate remain inside an observed baseline.
- No checkout, delivery, webhook, or health route is hidden behind stale cache.

# Graxia production readiness evidence — 2026-09-19

This record intentionally contains no secret values and no payment or revenue
claim.

## Deployment

- Free public host (current): `https://bravforcode.github.io/graxia/`
- Published artifact repository: `https://github.com/bravforcode/graxia`
- GitHub Pages status: `built`, HTTPS enforced, custom domain: none
- This is a free provider subpath, not an owned custom root domain. No
  `vercel.app` URL is used as the public site.
- The following Vercel deployment details are historical evidence from the
  earlier infrastructure and are not the current public URL:

- Vercel project: `phirawits-projects/graxia-os-funnel`
- Production deployment: `dpl_FYEa12si89Yaut1PaB7SnGSCB8C7`
- Deployment status: `Ready`
- Public canonical is now the GitHub Pages URL above; `graxia.store` is not
  owned or used.
- Store API bundle: `73.49 MB`
- Traffic capacity layer deployed in `dpl_9Xv6dCifEbj2KELx7VSxcsR3ZXih`:
  public HTML/assets/sitemap/robots receive cache headers; health remains
  non-cacheable.
- Baseline probe before cache: public HTML ~258–422 ms over three requests;
  `/api/v1/system/health` showed a cold-start spike up to ~14.6 s. This is a
  diagnostic sample, not a capacity or traffic guarantee.
- Previous bundle failure: `392.08 MB > 225 MB`; fixed by excluding caches,
  tests, worktrees, and local artifacts in `.vercelignore`.

## Public host smoke evidence

Verified on the free public host:

- `/` — HTTP 200
- `/store` and other client-side routes — GitHub Pages returns HTTP 404 but
  serves the app's `404.html` SPA fallback with the root mount and base-path
  assets; browser navigation can continue without a server 504.
- `/sitemap.xml` — HTTP 200
- `/robots.txt` — HTTP 200
- Main JS/CSS assets — HTTP 200

The free host is static-only. Checkout, lead capture, delivery, analytics
writes, and webhooks are not claimed as live on this host until a separate
non-Vercel API provider is authorized and deployed.
- System health returned `status=ok`, `readiness.is_ready=true`,
  `readiness.mode=running`, and zero readiness issues.
- Production HTML contains the temporary Vercel canonical URL and no old
  `graxia.store` canonical URL.
- Production sitemap contains 24 current-alias URLs; robots points to the
  current-alias sitemap.

No Stripe checkout or charge was executed as part of this verification.

## Database migration

- Target selected from Vercel Production Environment Variables.
- Observed before upgrade: `024_organic_attribution_consent (mergepoint)`.
- Upgrade completed through `029_funnel_lead_magnet_runtime_table`.
- Observed after upgrade: `029_funnel_lead_magnet_runtime_table (head)`.
- The first upgrade attempt exposed a legacy `alembic_version.version_num`
  `varchar(32)` limit; migration `025_conversion_event_touch_attribution`
  now expands that column to 64 characters before recording the longer growth
  revision IDs. The second production run completed all five upgrades.
- Production env was pulled to a temporary file and deleted after the run.
- A disposable SQLite migration check cannot run the existing PostgreSQL
  baseline because migration `002` requires `pgcrypto`; production/staging
  migration evidence therefore remains pending a PostgreSQL target.
- The repository-wide destructive-migration checker still reports pre-existing
  unannotated patterns in migrations `002`, `003`, `004`, `019`, and the legacy
  orchestration migration; none of the Growth OS migrations `025`–`029` match.

## Catalog and delivery assets

- Ten AI Factory products are `published` with `published_at` set.
- Each has one active content delivery asset with non-empty body content.
- Production asset body SHA-256 matched the local manifest for all ten
  products.
- Assets were generated from existing `ai-factory/downloads` source files;
  the AI Factory repository was not modified.
- Source and bundle hashes are recorded in
  `backend/assets/catalog/manifest.json`.
- Three new lead magnets are `published` and linked to target products:
  `prompt-pack-lite`, `freelance-pricing-calculator-lite`, and
  `n8n-sme-automation-checklist`.

## Secrets and providers

- Vercel Production contains encrypted entries for database, app security,
  Stripe configuration, admin auth, and `RESEND_API_KEY`.
- Production URL and payment safety flags were set without exposing secret
  values: `APP_BASE_URL`, `FRONTEND_URL`, `ALLOWED_CORS_ORIGINS`,
  `PUBLIC_FUNNEL_ORGANIZATION_ID`, `REVENUE_BRIDGE_HMAC_SECRET` (sensitive),
  `NO_LIVE_PAYMENT_MODE=true`, and `ALLOW_LIVE_STRIPE=false`.
- Existing local Graxia provider values were imported only for missing
  production names; the imported values were not printed and provider
  authorization was not claimed. Verified imported names include AI/search,
  Google, OpenClaw, Redis, Sentry, Supabase, Telegram, and site-automation
  integrations.
- Local-only, staging-only, and quant/trading environment entries were not
  copied into this Graxia Vercel production deployment.
- Secret values were not printed or copied into the repository.
- The secure operator script is
  `scripts/set-vercel-production-secrets.ps1`; blank prompts are skipped and
  secret values are never written to a local `.env` file.
- Render provider credentials and Render service deployment remain
  unverified because no Render CLI/API session is authenticated locally.

## DNS blocker

The temporary canonical surface is `https://graxia-os-funnel.vercel.app`.
`graxia.store` is attached to the Vercel project, but DNS is not configured
from the verification host; the app therefore continues to publish the
temporary Vercel URL in canonical, sitemap, and robots metadata.
Vercel requests this registrar-side record:

```text
A  graxia.store  76.76.21.21
```

The registrar is third-party and no DNS provider session is available here.
After adding the record, re-run `vercel domains inspect graxia.store` and
verify `https://graxia.store/` before changing any redirect or canonical
assumption.

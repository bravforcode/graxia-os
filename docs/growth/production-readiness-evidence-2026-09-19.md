# Graxia production readiness evidence — 2026-09-19

This record intentionally contains no secret values and no payment or revenue
claim.

## Deployment

- Vercel project: `phirawits-projects/graxia-os-funnel`
- Production deployment: `dpl_5oMQb4nA4vg6YV3KEMqhS4PgAmX9`
- Deployment status: `Ready`
- Production alias: `https://graxia-os-funnel.vercel.app`
- Store API bundle: `72.79 MB`
- Traffic capacity layer deployed in `dpl_9Xv6dCifEbj2KELx7VSxcsR3ZXih`:
  public HTML/assets/sitemap/robots receive cache headers; health remains
  non-cacheable.
- Baseline probe before cache: public HTML ~258–422 ms over three requests;
  `/api/v1/system/health` showed a cold-start spike up to ~14.6 s. This is a
  diagnostic sample, not a capacity or traffic guarantee.
- Previous bundle failure: `392.08 MB > 225 MB`; fixed by excluding caches,
  tests, worktrees, and local artifacts in `.vercelignore`.

## Production smoke evidence

Verified on the production alias:

- `/` — HTTP 200
- `/store` — HTTP 200
- `/guides/ai-prompt-workflows` — HTTP 200
- `/free/prompt-pack-lite` — HTTP 200
- `/sitemap.xml` — HTTP 200
- `/robots.txt` — HTTP 200
- `/api/v1/system/health` — HTTP 200
- `/health` — HTTP 200
- System health returned `status=ok`, `readiness.is_ready=true`,
  `readiness.mode=running`, and zero readiness issues.
- Production HTML contains the temporary Vercel canonical URL and no old
  `graxia.store` canonical URL.
- Production sitemap contains 24 current-alias URLs; robots points to the
  current-alias sitemap.

No Stripe checkout or charge was executed as part of this verification.

## Database migration

- Target selected from Vercel Production Environment Variables.
- Observed before upgrade: `021_add_funnel_v5_models`.
- Upgrade completed through `024_organic_attribution_consent`.
- Observed after upgrade: `024_organic_attribution_consent (head)`.
- Production env was pulled to a temporary file and deleted after the run.

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
`graxia.store` is attached to the Vercel project, but DNS is not configured.
Vercel requests this registrar-side record:

```text
A  graxia.store  76.76.21.21
```

The registrar is third-party and no DNS provider session is available here.
After adding the record, re-run `vercel domains inspect graxia.store` and
verify `https://graxia.store/` before changing any redirect or canonical
assumption.

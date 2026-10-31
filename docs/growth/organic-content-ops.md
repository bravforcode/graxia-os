# Organic content operations

Canonical surface (temporary until DNS is configured): `https://graxia-os-funnel.vercel.app`.

The operating sequence is:

1. Research and draft.
2. Repurpose for SEO, short-form, Facebook/Instagram, LINE, and X.
3. Run claim and UTM/link checks.
4. Require human approval with an unexpired approval record.
5. Export a dry-run batch until provider credentials and consent evidence exist.
6. Canary publish only after provider allowlist, consent, idempotency, and claim gates pass.
7. Review attribution and conversion events before the next batch.

Ruflo/content-ops must keep live publishing denied by default. The daily unit is
one approval batch; no provider token belongs in source control.

Lead magnets currently planned:

- Prompt Pack Lite
- Freelance Pricing Calculator Lite
- N8N/SME Automation Checklist

Public organic surfaces:

- `/guides/ai-prompt-workflows`
- `/guides/freelance-pricing-systems`
- `/guides/sme-automation-systems`
- `/free/prompt-pack-lite`
- `/free/freelance-pricing-calculator-lite`
- `/free/n8n-sme-automation-checklist`

Before enabling capture in an environment, publish the three corresponding
backend records with the fail-closed seed command:

```powershell
cd "C:\Users\menum\graxia os\backend"
python scripts/seed_organic_lead_magnets.py --base-url https://<verified-api-host>
```

The command refuses to publish a magnet when its target product is missing.

The ten AI Factory catalog rows use a separate fail-closed seed command. It
requires operator-supplied delivery files named after the catalog slug; no
placeholder asset is accepted:

```powershell
cd "C:\Users\menum\graxia os\backend"
python scripts/seed_graxia_catalog.py `
  --base-url https://<verified-api-host> `
  --asset-dir C:\path\to\graxia-assets
```

All claims are checked against `claims-ledger.yml`. Missing evidence means the
claim is omitted or marked as unverified.

# Ai Factory → Revenue OS catalog runbook

Status: `LOCAL_CONTRACT_READY — APPLY_AND_LIVE_EVIDENCE_PENDING`

The static `ai-factory` storefront owns display copy and reviewed THB prices.
Revenue OS owns the server-side product row, Stripe identifiers, and private
fulfillment object key. The browser never supplies an amount or a download URL.

## Check the reviewed catalog

Run from the Graxia OS repository:

```powershell
python -m scripts.revenue_os.ai_factory_catalog `
  --catalog "C:\Users\menum\ai-factory\products.json"
```

For a full preflight, create a local-only JSON file outside Git with exactly one
`ai-factory/<slug>...` private object key per slug:

```json
{
  "01-prompt-pack-th": "ai-factory/01-prompt-pack-th.zip",
  "02-obsidian-student-kit": "ai-factory/02-obsidian-student-kit.zip"
}
```

The real file must contain all ten approved slugs. Do not put bucket URLs,
public download paths, credentials, or customer data in it. Then run:

```powershell
python -m scripts.revenue_os.ai_factory_catalog `
  --catalog "C:\Users\menum\ai-factory\products.json" `
  --private-keys "C:\secure\ai-factory-private-object-keys.json"
```

Both commands are check-only and perform no provider calls.

## Reconcile a database

After migration `0012_product_private_metadata.sql` has been applied to the
intended environment, explicitly run the idempotent upsert with that
environment's `DATABASE_URL`:

```powershell
$env:APP_ENV = "staging"
python -m scripts.revenue_os.ai_factory_catalog `
  --catalog "C:\Users\menum\ai-factory\products.json" `
  --private-keys "C:\secure\ai-factory-private-object-keys.json" `
  --apply
```

The command updates only the ten Ai Factory slugs. Existing Stripe product/price
identifiers are preserved. It does not create Stripe objects, upload files,
deploy services, or charge a card. Production additionally requires the
explicit `--confirm-production` flag.

## Live-money gate

Do not set `ai-factory/checkout-config.js` to a public Revenue OS API until all
of the following have a redacted receipt:

- all ten rows exist as `PUBLISHED` with the reviewed THB amount;
- all ten rows have a private object key and no public fulfillment URL;
- Stripe test/live identifiers are reconciled server-side;
- staging and production checkout/webhook/fulfillment evidence is complete;
- one approved canary proves charge, webhook, order, ledger, entitlement,
  delivery, and reconciliation.

The catalog contract alone is not evidence that live money has been accepted.

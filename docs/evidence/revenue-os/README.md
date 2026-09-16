# Revenue OS evidence runner

The evidence runner records redacted gate receipts. It never deploys, charges,
publishes, or calls Stripe/Render/storage providers.

## Local database-backed tests

Start only the disposable local services:

```powershell
docker compose -f docker-compose.revenue-os-test.yml up -d
$env:DATABASE_URL = "postgresql+asyncpg://graxia:graxia_test_only@localhost:55432/revenue_os_test"
$env:REDIS_URL = "redis://localhost:56379/0"
python -m pytest graxia/packages/revenue_os/tests -q
docker compose -f docker-compose.revenue-os-test.yml down
```

The fixed password is local test data only. Never reuse it in staging or
production.

## Record one gate

Provide a source SHA, immutable artifact digest or local artifact, and a
redacted log hash. The command records supplied results; it does not execute
the gate command.

```powershell
python -m scripts.revenue_os.evidence_runner record-receipt `
  --gate staging-auth `
  --environment staging `
  --result passed `
  --command "pytest staging auth contract" `
  --source-sha <40-lowercase-hex> `
  --artifact-digest sha256:<64-lowercase-hex> `
  --output docs/evidence/revenue-os/<release>/receipts/staging-auth.json
```

Do not put API keys, emails, card numbers, raw provider IDs, or raw logs in a
receipt. A `go` manifest is valid only after every required gate is recorded as
`passed` against the same source and artifact identity.

## Build a release manifest

After all receipts are written, build the manifest from the receipt directory.
The command re-validates every receipt and binds it to one source SHA,
artifact digest, and environment. It defaults to `blocked`; use `--decision go`
only when every `--required-gate` is `passed`.

```powershell
python -m scripts.revenue_os.evidence_runner build-manifest `
  --release-id 2026-09-17-rc1 `
  --environment staging `
  --receipt-dir docs/evidence/revenue-os/2026-09-17-rc1/receipts `
  --output docs/evidence/revenue-os/2026-09-17-rc1/manifest.json `
  --source-sha <40-lowercase-hex> `
  --artifact-digest sha256:<64-lowercase-hex> `
  --required-gate staging-auth `
  --required-gate staging-checkout
```

This is an evidence operation only. It does not run gates, deploy, charge,
publish, or contact a provider.

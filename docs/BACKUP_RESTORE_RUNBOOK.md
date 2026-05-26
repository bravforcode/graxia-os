# Backup Restore Runbook

## Minimum Coverage

- database backup source identified
- restore target/environment identified
- migration head recorded before restore

## Backup Verification

1. create backup outside repo
2. verify artifact exists
3. record timestamp and owner

## Restore Verification

1. restore into non-production target first
2. run `alembic -c alembic.ini heads`
3. run health/readiness checks

## Stop Conditions

- unknown backup age
- schema mismatch
- failed restore smoke

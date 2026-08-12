# Phase 17 — Backup / Rollback Dry-Run

> Dry-run procedures only. No production database is ever touched.

## Prerequisites

- PostgreSQL client (`pg_dump`, `pg_restore`)
- Alembic (managed via `alembic_safe.py`)
- Backup encryption key configured (age-based encryption)
- Write access to the staging backup directory (`backups/`)

## Dry-Run Backup Command (placeholders)

```bash
# Local staging DB backup
pg_dump "postgresql://user:password@localhost:5432/graxia_staging" \
  --format=custom \
  --file="backups/staging_$(date +%Y%m%d_%H%M%S).dump"

# Compressed + encrypted backup
pg_dump "postgresql://user:password@localhost:5432/graxia_staging" \
  --format=custom \
  --compress=9 \
  --file="backups/staging_backup.dump"

# Verify backup integrity
pg_restore --list "backups/staging_backup.dump" > /dev/null 2>&1 && echo "Backup OK"
```

## Dry-Run Restore

```bash
# Never run against production. Staging-only example:
pg_restore --dbname="postgresql://user:password@localhost:5432/graxia_staging_restore" \
  --clean --if-exists \
  "backups/staging_backup.dump"

# Run schema-only verification
pg_restore --schema-only \
  --dbname="postgresql://user:password@localhost:5432/graxia_staging_verify" \
  "backups/staging_backup.dump"
```

## Migration Verification

```bash
# Check current state
alembic current

# Check history
alembic history

# Run pending migrations (staging only)
alembic upgrade head

# Verify migration was applied
alembic current
```

## Rollback Decision Tree

```
                    ┌──────────────────────────┐
                    │   Deployment Failure?     │
                    └────────────┬─────────────┘
                                 │
                    ┌────────────┴─────────────┐
                    │ YES                       │ NO
                    │                           │
         ┌──────────▼──────────┐     ┌─────────▼──────────┐
         │ DB migration        │     │ Continue monitoring│
         │ already applied?    │     │ for 15 min         │
         └──────────┬──────────┘     └────────────────────┘
                    │
         ┌──────────┴──────────┐
         │ YES                 │ NO
         │                     │
      ┌──▼──────────┐    ┌────▼────────┐
      │ Rollback    │    │ Revert      │
      │ DB first    │    │ code only   │
      │ alembic     │    │ (docker     │
      │ downgrade -1│    │  restart)   │
      └─────────────┘    └─────────────┘
```

## No Destructive Migration Policy

**Rules:**
1. All migrations must be **reversible** (`downgrade()` function required).
2. No `DROP COLUMN` without a 2-phase migration (add `deprecated_` prefix first).
3. No `DROP TABLE` in the same migration that creates a replacement.
4. Data migrations must be in **separate migrations** from schema changes.
5. Always run `check_destructive_migrations.py` before applying:

```bash
python scripts/ops/check_destructive_migrations.py
```

## Verification Commands

```bash
# Check Alembic head matches expected
alembic heads | grep "021_add_funnel_v5_models"

# No unapplied migrations
alembic current | grep "(head)"

# Backup file exists and is non-empty
ls -lh backups/staging_backup.dump
```

## Safe Rollback Procedure

```bash
# 1. Identify the migration to rollback
alembic history

# 2. Execute rollback
alembic downgrade -1

# 3. Verify rollback
alembic current

# 4. NOTIFY team (if applicable)
```

## What NOT to Do

- ❌ Do not run `pg_dump` or `pg_restore` against Supabase production
- ❌ Do not use `--clean` in production (drops all data before restore)
- ❌ Do not downgrade migrations that affect data integrity
- ❌ Do not skip `check_destructive_migrations.py`
- ❌ Do not restore backups without verifying backup integrity first

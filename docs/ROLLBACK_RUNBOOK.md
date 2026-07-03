# Rollback Runbook

> Procedures for rolling back code and database changes in production.
> **Always assess impact before rolling back — data loss or service disruption may occur.**

## Rollback Decision Tree

```
Is the issue in code, database, or both?
│
├── Code only (bug, regression, or config error)
│   └──→ Option A: Rollback Docker Compose
│
├── Database + Code (migration caused issue)
│   ├── Was migration additive only (CREATE TABLE, ADD COLUMN)?
│   │   └──→ Option B: Rollback code only, keep migration
│   └── Was migration destructive (DROP, ALTER that removed data)?
│       └──→ Option C: Full code + database rollback (requires restore)
│
└── Database only (corruption, accidental data loss)
    └──→ Option C: Database restore + matching code version
```

## Option A: Rollback Docker Compose (Code Only)

Use when the issue is in application code and no schema change needs reverting.

```bash
# 1. Revert to previous git tag or commit
git checkout <previous-stable-tag>

# 2. Rebuild and restart
docker compose -f docker-compose.yml -f config/docker-compose.production.yml up -d --build

# 3. Verify health
curl -s http://localhost:8000/health | python -m json.tool
```

## Option B: Keep Migration, Rollback Code

Use when a database migration is backward-compatible (additive only) but the application code has a bug.

```bash
# 1. Revert code only
git checkout <previous-stable-tag> -- backend/
git checkout <previous-stable-tag> -- frontend/

# 2. Rebuild backend and frontend
docker compose stop backend frontend
docker compose build backend frontend
docker compose up -d backend frontend

# 3. Verify application works with new DB schema
curl -s http://localhost:8000/health | python -m json.tool

# 4. If the code release is a minor revision that handled the new schema,
#    the old code should gracefully ignore unrecognized columns.
```

## Option C: Full Code + Database Rollback

Use when a migration is destructive or the schema change is incompatible with old code.

> **⚠️ WARNING:** This option may result in data loss for any data created or modified
> since the rollback target. Proceed only after verifying the backup is current.

```bash
# 1. Stop all services
docker compose down

# 2. Revert code
git checkout <previous-stable-tag>

# 3. Restore database from backup (see BACKUP_RESTORE_RUNBOOK.md)
#    IMPORTANT: Ensure the backup was taken BEFORE the bad migration

# 4. Rebuild and restart
docker compose -f docker-compose.yml -f config/docker-compose.production.yml up -d --build

# 5. Verify health
curl -s http://localhost:8000/health | python -m json.tool

# 6. Verify data integrity
curl -s http://localhost:8000/api/v1/health/readiness | python -m json.tool
```

## Option D: Migration Downgrade Only

Use when a single migration needs reverting and the code can still work.

```bash
# 1. Check current revision
docker compose exec backend alembic current

# 2. Review migration history
docker compose exec backend alembic history

# 3. Downgrade one step
docker compose exec backend python scripts/ops/alembic_safe.py downgrade -1

# 4. Verify the downgrade
docker compose exec backend alembic current

# 5. Verify application health
curl -s http://localhost:8000/health | python -m json.tool
```

## No Destructive Migration Policy

- ✅ **Allowed:** CREATE TABLE, ADD COLUMN, CREATE INDEX, CREATE UNIQUE INDEX
- ✅ **Allowed with caution:** ALTER TABLE ADD CONSTRAINT (ensure no existing violations)
- ❌ **Not allowed:** DROP TABLE, DROP COLUMN, ALTER COLUMN TYPE (unless data preserved)
- ❌ **Not allowed:** RENAME TABLE, RENAME COLUMN (use ADD NEW + migrate data instead)
- ⚠️ **Requires review:** ALTER COLUMN SET NOT NULL (ensure no NULLs exist)

If a destructive migration is absolutely required, it must:
1. Be in a separate migration file (not combined with additive changes)
2. Be reviewed by a second developer
3. Include a backup step in the migration script
4. Have a clear rollback script
5. Be deployed during a maintenance window

## Post-Rollback Verification

- [ ] Health endpoint returns 200
- [ ] Readiness endpoint shows no blockers
- [ ] All critical API routes respond
- [ ] Database connectivity confirmed
- [ ] Redis connectivity confirmed
- [ ] Auth/login flow works
- [ ] Rate limiting active
- [ ] Audit events being logged
- [ ] Monitoring dashboards updated

# Backup & Restore Runbook

> Procedures for backing up and restoring the Graxia OS PostgreSQL database.
> **Never run these commands against a live production database without explicit go/no-go approval.**

## RPO/RTO Targets

| Metric | Target | Notes |
|--------|--------|-------|
| RPO (Recovery Point Objective) | < 24 hours | Daily automated backups |
| RTO (Recovery Time Objective) | < 4 hours | Full restore from backup |

## Backup

### Automated Backup (Docker)

```bash
# Run backup using Docker Compose
docker compose exec -T db pg_dump -U graxia -d graxia_revenue_os -F c -Z 9 \
  -f /backups/graxia_$(date +%Y%m%d_%H%M%S).dump

# Verify backup file exists
docker compose exec db ls -la /backups/
```

### Automated Backup (Standalone)

```bash
# Using backup script
bash scripts/ops/backup_database.sh

# Manual pg_dump
pg_dump -h localhost -U graxia -d graxia_revenue_os -F c -Z 9 \
  -f backups/graxia_$(date +%Y%m%d_%H%M%S).dump
```

### Backup Verification

```bash
# Check backup file integrity
pg_restore -l backups/graxia_*.dump | head -20

# Verify backup contains expected tables
pg_restore -l backups/graxia_*.dump | grep -E "TABLE DATA|TABLE" | head -30
```

### Backup Rotation

- Keep last 7 daily backups locally
- Keep last 4 weekly backups in S3
- Keep last 12 monthly backups in S3 (encrypted)
- Delete backups older than 1 year

## Restore

### Prerequisites

- Target database must be empty or you must be prepared to overwrite
- Target database user must have `CREATE DATABASE` privileges
- Sufficient disk space for restore (typically 1.5x backup size)

### Restore Procedure

```bash
# 1. Stop services that access the database
docker compose stop backend worker-critical worker-default

# 2. Drop and recreate the database
docker compose exec db psql -U graxia -c "DROP DATABASE IF EXISTS graxia_revenue_os;"
docker compose exec db psql -U graxia -c "CREATE DATABASE graxia_revenue_os OWNER graxia;"

# 3. Restore from backup
docker compose exec -T db pg_restore -U graxia -d graxia_revenue_os \
  -F c -j 4 --no-owner --no-privileges \
  < backups/graxia_YYYYMMDD_HHMMSS.dump

# 4. Verify restore
docker compose exec db psql -U graxia -d graxia_revenue_os \
  -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"

# 5. Restart services
docker compose start backend worker-critical worker-default

# 6. Verify application health
curl -s http://localhost:8000/health | python -m json.tool
```

### Restore from S3

```bash
# 1. Download backup from S3
aws s3 cp s3://graxia-backups/production/graxia_YYYYMMDD_HHMMSS.dump.enc \
  backups/restore_temp.dump.enc

# 2. Decrypt (if encrypted)
# age --decrypt -i /path/to/age-key.txt -o backups/restore_temp.dump \
#   backups/restore_temp.dump.enc

# 3. Follow standard restore procedure above
```

## Rollback

See `docs/ROLLBACK_RUNBOOK.md` for full rollback procedures including code rollback + database migration downgrade.

## Testing Restore (Dry Run)

```bash
# Restore to a separate database for verification
docker compose exec db psql -U graxia -c "CREATE DATABASE graxia_restore_test OWNER graxia;"
docker compose exec -T db pg_restore -U graxia -d graxia_restore_test \
  -F c -j 4 --no-owner --no-privileges \
  < backups/graxia_YYYYMMDD_HHMMSS.dump

# Verify data integrity
docker compose exec db psql -U graxia -d graxia_restore_test \
  -c "SELECT table_name, num_rows FROM information_schema.tables;"

# Drop test database
docker compose exec db psql -U graxia -c "DROP DATABASE graxia_restore_test;"
```

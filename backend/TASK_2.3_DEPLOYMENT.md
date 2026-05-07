# TASK 2.3 Deployment Guide: Add Database Indexes for Common Query Patterns [H-03]

## Overview

This deployment adds 17 composite indexes to optimize common query patterns across 4 core tables:
- **opportunities**: 4 composite indexes
- **contacts**: 4 composite indexes  
- **email_threads**: 3 composite indexes
- **assistant_tasks**: 5 composite indexes

All indexes are created using `CREATE INDEX CONCURRENTLY` to avoid table locks during deployment.

## Pre-Deployment Checklist

### 1. Backup Database

```bash
# Create a backup before migration
pg_dump -h <host> -U <user> -d <database> -F c -f backup_before_indexes_$(date +%Y%m%d_%H%M%S).dump
```

### 2. Check Database Space

```bash
# Verify available disk space (indexes will add ~5-10% to database size)
df -h /var/lib/postgresql/data

# Check current database size
psql -h <host> -U <user> -d <database> -c "
SELECT pg_size_pretty(pg_database_size(current_database())) as db_size;
"
```

### 3. Run Benchmark (Before)

```bash
cd backend
python scripts/benchmark_queries.py --before --iterations 10
```

This creates `backend/scripts/benchmark_before.json` with baseline performance metrics.

## Deployment Steps

### Step 1: Review Migration

```bash
# Review the migration file
cat backend/alembic/versions/018_add_composite_query_indexes.py
```

### Step 2: Test on Staging

```bash
# Set staging database URL
export DATABASE_URL="postgresql+asyncpg://user:pass@staging-host:5432/graxia_staging"

# Run migration
cd backend
alembic upgrade head

# Verify indexes were created
python scripts/verify_indexes.py
```

### Step 3: Run Benchmark (After - Staging)

```bash
python scripts/benchmark_queries.py --after --iterations 10
python scripts/benchmark_queries.py --compare
```

Expected results:
- ✅ Query performance improved >50% for filtered list operations
- ✅ Database size increased <10%
- ✅ All indexes created successfully

### Step 4: Deploy to Production

**IMPORTANT**: This migration uses `CREATE INDEX CONCURRENTLY` which:
- ✅ Does NOT lock tables
- ✅ Allows normal read/write operations during index creation
- ⚠️  Takes longer than regular index creation
- ⚠️  Requires autocommit mode (cannot run in transaction)

```bash
# Set production database URL
export DATABASE_URL="postgresql+asyncpg://user:pass@prod-host:5432/graxia_prod"

# Run migration
cd backend
alembic upgrade head
```

**Expected Duration**: 2-5 minutes depending on table sizes.

### Step 5: Verify Production Deployment

```bash
# Verify all indexes were created
python scripts/verify_indexes.py

# Run performance benchmark
python scripts/benchmark_queries.py --after --iterations 10
python scripts/benchmark_queries.py --compare
```

## Monitoring

### Check Index Creation Progress

While migration is running, you can monitor progress:

```sql
-- Check for index creation in progress
SELECT 
    pid,
    now() - pg_stat_activity.query_start AS duration,
    query
FROM pg_stat_activity
WHERE query LIKE '%CREATE INDEX%'
    AND state = 'active';
```

### Check Index Sizes

```sql
-- Check sizes of new indexes
SELECT
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) as size
FROM pg_stat_user_indexes
WHERE indexname LIKE 'idx_%'
    AND tablename IN ('opportunities', 'contacts', 'email_threads', 'assistant_tasks')
ORDER BY pg_relation_size(indexrelid) DESC;
```

### Monitor Index Usage

```sql
-- Check if indexes are being used (after some queries run)
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan as scans,
    idx_tup_read as tuples_read,
    pg_size_pretty(pg_relation_size(indexrelid)) as size
FROM pg_stat_user_indexes
WHERE indexname LIKE 'idx_%'
    AND tablename IN ('opportunities', 'contacts', 'email_threads', 'assistant_tasks')
ORDER BY idx_scan DESC;
```

## Rollback Procedure

If issues occur, rollback the migration:

```bash
# Rollback to previous version
cd backend
alembic downgrade -1

# Verify indexes were removed
python scripts/verify_indexes.py
```

**Note**: Rollback also uses `DROP INDEX CONCURRENTLY` to avoid table locks.

## Troubleshooting

### Issue: Migration Hangs

**Cause**: Long-running queries blocking index creation.

**Solution**:
```sql
-- Check for blocking queries
SELECT pid, query, state, wait_event_type, wait_event
FROM pg_stat_activity
WHERE state = 'active' AND query NOT LIKE '%pg_stat_activity%';

-- If needed, terminate blocking query (use with caution)
SELECT pg_terminate_backend(pid);
```

### Issue: "CONCURRENTLY cannot be used in a transaction"

**Cause**: Alembic trying to run in transaction mode.

**Solution**: The migration uses `op.get_bind().execute()` which handles this automatically. If you see this error, ensure you're using the latest Alembic version.

### Issue: Index Creation Failed

**Cause**: Insufficient disk space or invalid data.

**Solution**:
```sql
-- Check for invalid indexes
SELECT
    schemaname,
    tablename,
    indexname,
    pg_get_indexdef(indexrelid) as definition
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
    AND indexname LIKE 'idx_%'
    AND NOT pg_index.indisvalid
FROM pg_index
WHERE pg_index.indexrelid = pg_stat_user_indexes.indexrelid;

-- Drop and recreate invalid index
DROP INDEX CONCURRENTLY IF EXISTS <index_name>;
-- Then re-run migration
```

### Issue: Performance Not Improved

**Cause**: Query planner not using new indexes.

**Solution**:
```sql
-- Update table statistics
ANALYZE opportunities;
ANALYZE contacts;
ANALYZE email_threads;
ANALYZE assistant_tasks;

-- Check if indexes are being used
EXPLAIN ANALYZE
SELECT * FROM opportunities
WHERE user_id = '<uuid>' AND status = 'found' AND is_deleted = false;
```

## Acceptance Criteria Verification

After deployment, verify all acceptance criteria are met:

### ✅ 1. Migration runs without long table locks (< 5 min)

```bash
# Check migration duration from logs
# Should complete in 2-5 minutes
```

### ✅ 2. Query performance improved >50%

```bash
# Compare benchmark results
python scripts/benchmark_queries.py --compare

# Should show >50% improvement for filtered list operations
```

### ✅ 3. Database size increased <10%

```bash
# Check size increase
python scripts/verify_indexes.py

# Compare "Indexes Size" before and after
# Should be <10% increase
```

### ✅ 4. Rollback works correctly

```bash
# Test rollback on staging
alembic downgrade -1
python scripts/verify_indexes.py  # Should show missing indexes

# Re-apply
alembic upgrade head
python scripts/verify_indexes.py  # Should show all indexes present
```

## Post-Deployment

### 1. Monitor Query Performance

Use application monitoring tools to track:
- API response times for list endpoints
- Database query duration
- Index usage statistics

### 2. Update Statistics

```sql
-- Run ANALYZE to update query planner statistics
ANALYZE opportunities;
ANALYZE contacts;
ANALYZE email_threads;
ANALYZE assistant_tasks;
```

### 3. Document Results

Update `TASK_2.3_SUMMARY.md` with:
- Actual deployment duration
- Performance improvements measured
- Database size increase
- Any issues encountered

## Support

For issues or questions:
1. Check troubleshooting section above
2. Review Alembic logs: `backend/alembic.log`
3. Check PostgreSQL logs for index creation errors
4. Contact: Backend Team / DBA

## References

- Migration file: `backend/alembic/versions/018_add_composite_query_indexes.py`
- Benchmark script: `backend/scripts/benchmark_queries.py`
- Verification script: `backend/scripts/verify_indexes.py`
- PostgreSQL CONCURRENT indexes: https://www.postgresql.org/docs/current/sql-createindex.html#SQL-CREATEINDEX-CONCURRENTLY

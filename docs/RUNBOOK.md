# Graxia OS Enterprise Runbook

## Production Operations Guide

---

## Table of Contents

1. [Deployment](#deployment)
2. [Monitoring](#monitoring)
3. [Incident Response](#incident-response)
4. [Database Operations](#database-operations)
5. [Backup & Recovery](#backup--recovery)
6. [Security](#security)
7. [Troubleshooting](#troubleshooting)

---

## Deployment

### Pre-Deployment Checklist

- [ ] All tests passing (`pytest tests/ -v`)
- [ ] Database migrations reviewed (`alembic history`)
- [ ] Secrets configured in Fly.io (`fly secrets list`)
- [ ] Health checks verified locally (`curl http://localhost:8000/health`)
- [ ] Sentry DSN configured (production error tracking)
- [ ] Backup strategy verified

### Production Deployment

```bash
# 1. Run all tests
pytest tests/ -v

# 2. Check database migrations
alembic current
alembic history

# 3. Deploy to Fly.io
fly deploy --app graxia-api --strategy rolling

# 4. Verify deployment
fly status --app graxia-api
curl https://graxia-api.fly.dev/health

# 5. Run database migrations (if needed)
DATABASE_URL=$(fly secrets get DATABASE_URL) alembic upgrade head
```

### Rollback Procedure

```bash
# Emergency rollback
fly deploy --app graxia-api --image graxia-api:deployment-<PREVIOUS_VERSION>

# Verify rollback
fly status --app graxia-api
```

---

## Monitoring

### Health Endpoints

| Endpoint | Purpose | Expected Response |
|----------|---------|-------------------|
| `/health` | Basic health check | `{"status":"ok"}` |
| `/system/stats` | System statistics | 200 OK (requires auth) |
| `/internal/health` | Internal health | Detailed health metrics |

### Sentry Error Tracking

- **DSN**: Configured via `SENTRY_DSN` environment variable
- **Sample Rates**: `SENTRY_TRACES_SAMPLE_RATE` (default 0.1)
- **Environments**: Tracks `APP_ENV` automatically

### Log Aggregation

```bash
# View production logs
fly logs --app graxia-api

# Filter for errors
fly logs --app graxia-api | grep ERROR
```

---

## Incident Response

### Severity Levels

- **P0 (Critical)**: Service down, data loss, security breach
- **P1 (High)**: Major feature degraded, no workaround
- **P2 (Medium)**: Partial degradation, workaround exists
- **P3 (Low)**: Minor issue, cosmetic

### P0 Response Procedure

1. **Acknowledge** (1 min)
   - Page on-call engineer
   - Create incident channel

2. **Assess** (5 min)
   - Check Fly.io status
   - Verify database connectivity
   - Review recent deployments

3. **Mitigate** (15 min)
   - Execute rollback if needed
   - Enable circuit breakers
   - Scale up resources

4. **Resolve** (60 min)
   - Root cause analysis
   - Fix and test
   - Deploy fix

### Emergency Contacts

- **Primary On-Call**: [Your contact]
- **Secondary**: [Backup contact]
- **Database Admin**: [DBA contact]
- **Fly.io Support**: https://fly.io/docs/super

---

## Database Operations

### Migration Commands

```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Review migration
alembic upgrade head --sql

# Apply migrations
alembic upgrade head

# Check current version
alembic current

# Rollback one version
alembic downgrade -1
```

### Database Health Check

```python
# Using app.database.check_db_health()
from app.database import check_db_health
import asyncio

result = asyncio.run(check_db_health())
print(result)
```

### Connection Pool Monitoring

```python
# Check pool status
from app.database import engine

if hasattr(engine.pool, 'size'):
    print(f"Pool size: {engine.pool.size()}")
    print(f"Checked in: {engine.pool.checkedin()}")
    print(f"Checked out: {engine.pool.checkedout()}")
```

---

## Backup & Recovery

### Automated Backups

Backups run automatically via scheduled tasks. Manual backup:

```bash
# Create encrypted backup
python scripts/backup_database.py pg_dump --s3-upload

# Verify backup
python scripts/backup_database.py verify --manifest <manifest-path>
```

### Restore Procedure

```bash
# 1. Stop application
fly scale count 0 --app graxia-api

# 2. Restore from backup
python scripts/backup_database.py restore --backup-id <backup-id>

# 3. Run migrations
alembic upgrade head

# 4. Start application
fly scale count 2 --app graxia-api

# 5. Verify
fly status --app graxia-api
curl https://graxia-api.fly.dev/health
```

### Disaster Recovery (DR)

- **RPO (Recovery Point Objective)**: 1 hour
- **RTO (Recovery Time Objective)**: 4 hours
- **Backup Location**: S3-compatible storage + local copies
- **Encryption**: age (modern encryption tool)

---

## Security

### Secret Rotation

```bash
# Rotate database password
fly secrets set DATABASE_URL="postgresql://..." --app graxia-api

# Rotate API keys
fly secrets set INTERNAL_API_KEY="$(openssl rand -hex 32)" --app graxia-api
```

### Security Monitoring

- **Failed Logins**: Monitored via audit logs
- **Rate Limiting**: Automatic (see middleware)
- **Suspicious Activity**: Alerted via Sentry

### SSL/TLS

- Certificates managed by Fly.io (auto-renewal)
- HSTS enabled for production domains
- Certificate expiry monitoring

---

## Troubleshooting

### Common Issues

#### Database Connection Failures

**Symptoms**: 500 errors, timeout messages

**Resolution**:
```bash
# Check pool status
fly ssh console --app graxia-api
python -c "from app.database import check_db_health; import asyncio; print(asyncio.run(check_db_health()))"

# Restart if needed
fly restart --app graxia-api
```

#### High Memory Usage

**Symptoms**: OOM errors, slow responses

**Resolution**:
```bash
# Check memory usage
fly status --app graxia-api

# Scale up memory
fly scale memory 2048 --app graxia-api
```

#### Redis Connection Issues

**Symptoms**: Rate limiting failures, cache misses

**Resolution**:
```bash
# Check Redis health
fly ssh console --app graxia-api
python -c "from app.core.redis_pool import ping_redis; import asyncio; print(asyncio.run(ping_redis()))"
```

### Debug Mode (Emergency)

```bash
# Enable debug logging (temporary)
fly secrets set LOG_LEVEL="DEBUG" --app graxia-api
fly restart --app graxia-api

# Revert after debugging
fly secrets set LOG_LEVEL="INFO" --app graxia-api
fly restart --app graxia-api
```

---

## Appendix

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `REDIS_URL` | Yes | Redis connection string |
| `SECRET_KEY` | Yes | JWT signing key |
| `SENTRY_DSN` | No | Error tracking DSN |
| `STRIPE_SECRET_KEY` | Yes | Payment processing |
| `RESEND_API_KEY` | Yes | Email service |

### Useful Commands

```bash
# SSH into production
fly ssh console --app graxia-api

# View environment
fly ssh console --app graxia-api -C "env | grep -E 'DATABASE|REDIS|SECRET'"

# Database console
fly ssh console --app graxia-api -C "python -c 'from app.database import engine; print(engine.url)'"

# Restart with zero downtime
fly deploy --strategy rolling
```

---

**Document Version**: 1.0  
**Last Updated**: 2026-05-06  
**Owner**: Graxia OS Team

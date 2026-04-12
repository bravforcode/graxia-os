# Troubleshooting Guide - Personal OS v3

Common issues and solutions for Personal OS.

## Table of Contents

1. [Database Issues](#database-issues)
2. [API Connection Issues](#api-connection-issues)
3. [Authentication Problems](#authentication-problems)
4. [Scraper Failures](#scraper-failures)
5. [Performance Issues](#performance-issues)
6. [Backup/Restore Issues](#backuprestore-issues)
7. [Frontend Issues](#frontend-issues)
8. [Scheduler Issues](#scheduler-issues)

## Database Issues

### Connection Refused

**Symptom:** `Connection refused` or `could not connect to server`

**Solutions:**

1. Check if PostgreSQL is running:
```bash
docker-compose ps postgres
# or
systemctl status postgresql
```

2. Verify DATABASE_URL in `.env`:
```env
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/personal_os
```

3. Test connection:
```bash
psql -U personal_os_user -d personal_os -h localhost
```

### Migration Errors

**Symptom:** `alembic upgrade head` fails

**Solutions:**

1. Check current revision:
```bash
alembic current
```

2. Downgrade and re-upgrade:
```bash
alembic downgrade -1
alembic upgrade head
```

3. Reset database (CAUTION: data loss):
```bash
alembic downgrade base
alembic upgrade head
```

### Slow Queries

**Symptom:** API responses taking >5 seconds

**Solutions:**

1. Check missing indexes:
```sql
SELECT schemaname, tablename, indexname
FROM pg_indexes
WHERE schemaname = 'public';
```

2. Analyze query performance:
```sql
EXPLAIN ANALYZE SELECT * FROM opportunities WHERE status = 'discovered';
```

3. Add indexes:
```sql
CREATE INDEX idx_opportunities_status ON opportunities(status);
```

## API Connection Issues

### 502 Bad Gateway

**Symptom:** Frontend shows "502 Bad Gateway"

**Solutions:**

1. Check backend is running:
```bash
docker-compose logs backend
curl http://localhost:8000/api/v1/system/health
```

2. Restart backend:
```bash
docker-compose restart backend
```

3. Check nginx configuration:
```bash
nginx -t
systemctl restart nginx
```

### CORS Errors

**Symptom:** Browser console shows CORS errors

**Solutions:**

1. Update `backend/app/main.py`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

2. Restart backend:
```bash
docker-compose restart backend
```

### Rate Limiting

**Symptom:** `429 Too Many Requests`

**Solutions:**

1. Check rate limit configuration in `backend/app/middleware/rate_limit.py`

2. Increase limits temporarily:
```python
RATE_LIMITS = {
    "default": "200/minute",  # Increased from 100
}
```

3. Clear rate limit cache:
```bash
docker-compose restart backend
```

## Authentication Problems

### Invalid Token

**Symptom:** `401 Unauthorized` or "Invalid token"

**Solutions:**

1. Check JWT_SECRET_KEY in `.env`:
```env
JWT_SECRET_KEY=your-secret-key-min-32-chars
```

2. Clear browser localStorage:
```javascript
localStorage.clear()
```

3. Generate new token:
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password"}'
```

### Token Expired

**Symptom:** "Token has expired"

**Solutions:**

1. Refresh token:
```bash
curl -X POST http://localhost:8000/api/v1/auth/refresh \
  -H "Authorization: Bearer <refresh_token>"
```

2. Increase token expiry in `backend/app/core/auth.py`:
```python
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours
```

## Scraper Failures

### OpenClaw API Errors

**Symptom:** Scrapers failing with API errors

**Solutions:**

1. Check API key:
```bash
echo $OPENCLAW_API_KEY
```

2. Test API directly:
```bash
curl -X POST https://api.openclaw.com/scrape \
  -H "Authorization: Bearer $OPENCLAW_API_KEY" \
  -d '{"url":"https://devpost.com"}'
```

3. Check rate limits:
```bash
curl http://localhost:8000/api/v1/system/health
```

### Scraper Timeouts

**Symptom:** Scrapers timing out

**Solutions:**

1. Increase timeout in scraper:
```python
async def scrape(self):
    async with httpx.AsyncClient(timeout=60.0) as client:  # Increased
        ...
```

2. Check network connectivity:
```bash
ping devpost.com
curl -I https://devpost.com
```

3. Use circuit breaker:
```python
from app.core.circuit_breaker import circuit_breaker

@circuit_breaker
async def scrape(self):
    ...
```

### No Results Found

**Symptom:** Scrapers run but find 0 items

**Solutions:**

1. Check scraper health:
```bash
curl http://localhost:8000/api/v1/system/health/scrapers
```

2. Test scraper manually:
```bash
cd backend
python -c "
from app.scrapers.devpost import DevpostScraper
import asyncio
scraper = DevpostScraper()
asyncio.run(scraper.scrape())
"
```

3. Check website structure (may have changed):
- Inspect target website
- Update selectors in scraper code

## Performance Issues

### High Memory Usage

**Symptom:** System using >4GB RAM

**Solutions:**

1. Check memory usage:
```bash
docker stats
```

2. Reduce worker count:
```bash
uvicorn app.main:app --workers 2  # Reduced from 4
```

3. Enable connection pooling:
```python
engine = create_async_engine(
    DATABASE_URL,
    pool_size=10,  # Reduced from 20
    max_overflow=5
)
```

### High CPU Usage

**Symptom:** CPU at 100%

**Solutions:**

1. Check running processes:
```bash
docker-compose top
```

2. Reduce scheduler frequency:
```python
# In backend/app/core/scheduler.py
scheduler.add_job(scan_opportunities, 'interval', hours=2)  # Increased from 1
```

3. Optimize database queries:
```sql
VACUUM ANALYZE;
```

### Slow API Responses

**Symptom:** API taking >2 seconds

**Solutions:**

1. Enable query logging:
```python
engine = create_async_engine(DATABASE_URL, echo=True)
```

2. Add database indexes (see Database Issues)

3. Enable caching:
```python
from functools import lru_cache

@lru_cache(maxsize=100)
def get_opportunities():
    ...
```

## Backup/Restore Issues

### Backup Fails

**Symptom:** `backup_database.py` fails

**Solutions:**

1. Check disk space:
```bash
df -h
```

2. Verify PostgreSQL access:
```bash
pg_dump --version
psql -U personal_os_user -d personal_os -c "SELECT 1"
```

3. Check S3 credentials:
```bash
aws s3 ls s3://personal-os-backups
```

### Restore Fails

**Symptom:** `restore_database.py` fails

**Solutions:**

1. Verify backup file:
```bash
gunzip -t backups/backup_YYYYMMDD_HHMMSS.sql.gz
```

2. Check database permissions:
```sql
GRANT ALL PRIVILEGES ON DATABASE personal_os TO personal_os_user;
```

3. Restore manually:
```bash
gunzip -c backups/backup_YYYYMMDD_HHMMSS.sql.gz | psql -U personal_os_user -d personal_os
```

## Frontend Issues

### Build Fails

**Symptom:** `npm run build` fails

**Solutions:**

1. Clear node_modules:
```bash
rm -rf node_modules package-lock.json
npm install
```

2. Check Node version:
```bash
node --version  # Should be 18+
```

3. Fix TypeScript errors:
```bash
npm run lint
```

### Page Not Loading

**Symptom:** Blank page or loading forever

**Solutions:**

1. Check browser console for errors

2. Verify API connection:
```javascript
// In browser console
fetch('http://localhost:8000/api/v1/system/health')
  .then(r => r.json())
  .then(console.log)
```

3. Clear browser cache:
- Chrome: Ctrl+Shift+Delete
- Firefox: Ctrl+Shift+Delete

### Charts Not Rendering

**Symptom:** Costs page charts not showing

**Solutions:**

1. Install recharts:
```bash
cd frontend
npm install recharts
```

2. Check data format:
```javascript
console.log(costsData)  // Should be array of objects
```

## Scheduler Issues

### Jobs Not Running

**Symptom:** Scheduled tasks not executing

**Solutions:**

1. Check scheduler status:
```bash
curl http://localhost:8000/api/v1/system/health/scheduler
```

2. View scheduler logs:
```bash
docker-compose logs backend | grep "scheduler"
```

3. Restart scheduler:
```bash
docker-compose restart backend
```

### Duplicate Job Executions

**Symptom:** Jobs running multiple times

**Solutions:**

1. Check for multiple backend instances:
```bash
docker-compose ps
```

2. Add job coalescing:
```python
scheduler.add_job(
    scan_opportunities,
    'interval',
    hours=1,
    coalesce=True,  # Prevent duplicate runs
    max_instances=1
)
```

## Getting Help

### Enable Debug Logging

```python
# In backend/app/main.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Check System Health

```bash
curl http://localhost:8000/api/v1/system/health
```

### View All Logs

```bash
# Backend logs
docker-compose logs -f backend

# Database logs
docker-compose logs -f postgres

# All logs
docker-compose logs -f
```

### Export Diagnostics

```bash
# System info
docker-compose ps > diagnostics.txt
docker stats --no-stream >> diagnostics.txt

# Logs
docker-compose logs --tail=1000 >> diagnostics.txt

# Database info
psql -U personal_os_user -d personal_os -c "\dt" >> diagnostics.txt
```

## Emergency Procedures

### System Unresponsive

```bash
# 1. Stop all services
docker-compose down

# 2. Clear volumes (CAUTION: data loss)
docker-compose down -v

# 3. Restore from backup
python backend/restore_database.py

# 4. Restart
docker-compose up -d
```

### Data Corruption

```bash
# 1. Stop backend
docker-compose stop backend

# 2. Restore database
python backend/restore_database.py

# 3. Verify data
psql -U personal_os_user -d personal_os -c "SELECT COUNT(*) FROM opportunities"

# 4. Restart
docker-compose start backend
```

## Prevention

### Regular Maintenance

```bash
# Daily
docker-compose logs --tail=100 | grep ERROR

# Weekly
python backend/backup_database.py
docker system prune -f

# Monthly
apt update && apt upgrade
docker-compose pull
```

### Monitoring Alerts

Setup alerts for:
- High error rates (>5%)
- Slow responses (>2s)
- High memory usage (>80%)
- Failed backups
- Scraper failures

See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for monitoring setup.

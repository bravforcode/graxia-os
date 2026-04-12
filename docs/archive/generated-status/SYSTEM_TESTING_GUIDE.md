# 🧪 System Testing Guide

## ภาพรวม

คู่มือนี้จะแนะนำวิธีการทดสอบระบบทั้งหมดอย่างละเอียด เพื่อให้แน่ใจว่าทุกส่วนทำงานได้อย่างสมบูรณ์

## 🎯 Test Coverage

### ✅ Unit Tests
- Configuration tests
- Model tests
- Utility function tests
- Policy tests
- Router tests

### ✅ Integration Tests
- Database operations
- Event bus
- Agent workflows
- API endpoints
- External integrations

### ✅ End-to-End Tests
- Complete opportunity lifecycle
- Submission workflow
- Contact management
- Obsidian sync

## 🚀 Running Tests

### ทั้งหมด

```bash
cd backend
pytest tests/ -v
```

### แบบเฉพาะเจาะจง

```bash
# Unit tests only
pytest tests/test_config.py -v
pytest tests/test_policy.py -v
pytest tests/test_model_router.py -v

# Integration tests
pytest tests/test_obsidian.py -v
pytest tests/test_comprehensive.py -v

# Specific test
pytest tests/test_config.py::test_development_host_rewrite_for_local_runs -v
```

### With Coverage

```bash
pytest tests/ --cov=app --cov-report=html
```

จากนั้นเปิด `htmlcov/index.html` เพื่อดู coverage report

## 📋 Test Checklist

### 1. Configuration Tests ✅

```bash
pytest tests/test_config.py -v
```

ทดสอบ:
- ✅ Environment variable loading
- ✅ Host rewriting for local development
- ✅ Placeholder detection
- ✅ Supabase URL normalization
- ✅ Database connection settings

### 2. Model Router Tests ✅

```bash
pytest tests/test_model_router.py -v
```

ทดสอบ:
- ✅ Task classification
- ✅ Model tier selection
- ✅ Cost estimation
- ✅ Budget guardrails
- ✅ Complexity-based routing

### 3. Policy Tests ✅

```bash
pytest tests/test_policy.py -v
```

ทดสอบ:
- ✅ Approval requirements
- ✅ Batch operations
- ✅ TTL settings
- ✅ Policy fallbacks

### 4. Obsidian Integration Tests ✅

```bash
pytest tests/test_obsidian.py -v
```

ทดสอบ:
- ✅ File creation
- ✅ Note writing
- ✅ Frontmatter generation
- ✅ Folder structure
- ✅ Daily notes
- ✅ Opportunity logging
- ✅ Submission logging
- ✅ Contact notes
- ✅ Weekly reviews

### 5. Comprehensive Integration Tests ✅

```bash
pytest tests/test_comprehensive.py -v
```

ทดสอบ:
- ✅ Opportunity lifecycle
- ✅ Contact creation and sync
- ✅ Event bus with multiple subscribers
- ✅ Scoring system
- ✅ Decision engine
- ✅ Learning engine
- ✅ Cost tracking
- ✅ Rate limiting
- ✅ Telegram notifications
- ✅ Google Workspace integration
- ✅ Scheduler jobs
- ✅ Database migrations
- ✅ API endpoints
- ✅ Full system integration

## 🔍 Manual Testing

### 1. Backend Health Check

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "ready",
  "service": "Personal OS v3",
  "readiness": {
    "is_ready": true,
    "mode": "ready",
    "issues": []
  }
}
```

### 2. API Documentation

เปิด browser: http://localhost:8000/docs

ทดสอบ endpoints:
- ✅ GET /health
- ✅ GET /api/v1/opportunities
- ✅ GET /api/v1/submissions
- ✅ GET /api/v1/contacts
- ✅ GET /api/v1/drafts
- ✅ GET /api/v1/metrics/current-week
- ✅ GET /api/v1/cognitive/today
- ✅ GET /api/v1/obsidian/health

### 3. Database Connection

```bash
# ใน Docker container
docker-compose exec backend python -c "
from app.database import engine
from sqlalchemy import text
with engine.connect() as conn:
    result = conn.execute(text('SELECT 1'))
    print('Database connected:', result.scalar())
"
```

### 4. Redis Connection

```bash
docker-compose exec redis redis-cli ping
```

Expected: `PONG`

### 5. Celery Worker

```bash
docker-compose logs celery
```

ตรวจสอบ:
- ✅ Worker started successfully
- ✅ Connected to broker
- ✅ No errors

### 6. Event Bus

```bash
# ใน Python shell
docker-compose exec backend python

>>> from app.core.event_bus import event_bus
>>> import asyncio
>>> async def test():
...     await event_bus.emit("test.event", {"data": "test"})
>>> asyncio.run(test())
```

### 7. Obsidian Integration

```bash
curl -X POST http://localhost:8000/api/v1/obsidian/daily-note
```

ตรวจสอบว่าไฟล์ถูกสร้างใน Obsidian vault

### 8. Telegram Bot (ถ้ามี token)

```bash
# ส่งข้อความทดสอบ
curl -X POST http://localhost:8000/api/v1/commands/execute \
  -H "Content-Type: application/json" \
  -d '{"command": "status"}'
```

### 9. Google Workspace (ถ้ามี credentials)

```bash
curl http://localhost:8000/api/v1/integrations/google/health
```

### 10. Scrapers

```bash
# ทดสอบ DevPost scraper
docker-compose exec backend python -c "
import asyncio
from app.scrapers.devpost import DevPostScraper
scraper = DevPostScraper()
asyncio.run(scraper.scrape())
"
```

## 🎯 Performance Testing

### Load Testing with Locust

1. ติดตั้ง Locust:

```bash
pip install locust
```

2. สร้าง `locustfile.py`:

```python
from locust import HttpUser, task, between

class PersonalOSUser(HttpUser):
    wait_time = between(1, 3)
    
    @task
    def health_check(self):
        self.client.get("/health")
    
    @task(3)
    def list_opportunities(self):
        self.client.get("/api/v1/opportunities")
    
    @task(2)
    def list_submissions(self):
        self.client.get("/api/v1/submissions")
    
    @task
    def current_metrics(self):
        self.client.get("/api/v1/metrics/current-week")
```

3. Run:

```bash
locust -f locustfile.py --host=http://localhost:8000
```

4. เปิด http://localhost:8089

### Database Performance

```sql
-- ตรวจสอบ slow queries
SELECT query, calls, total_time, mean_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;

-- ตรวจสอบ table sizes
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

## 🐛 Debugging

### Enable Debug Logging

ใน `.env`:

```bash
LOG_LEVEL=DEBUG
```

### View Logs

```bash
# Backend logs
docker-compose logs -f backend

# Celery logs
docker-compose logs -f celery

# All logs
docker-compose logs -f
```

### Database Queries

```bash
# Enable query logging
docker-compose exec postgres psql -U personal_os -d personal_os

personal_os=# SET log_statement = 'all';
personal_os=# \q
```

### Python Debugger

เพิ่มใน code:

```python
import pdb; pdb.set_trace()
```

หรือใช้ `breakpoint()` (Python 3.7+)

## 📊 Monitoring

### Health Checks

```bash
# Backend
curl http://localhost:8000/health

# Obsidian
curl http://localhost:8000/api/v1/obsidian/health

# Google Workspace
curl http://localhost:8000/api/v1/integrations/google/health
```

### Metrics

```bash
# Current week metrics
curl http://localhost:8000/api/v1/metrics/current-week

# Metric history
curl http://localhost:8000/api/v1/metrics/history?weeks=4

# Loss analysis
curl http://localhost:8000/api/v1/metrics/loss-analysis
```

### System Status

```bash
curl http://localhost:8000/api/v1/system/status
```

## 🔒 Security Testing

### 1. SQL Injection

ทดสอบว่า SQLAlchemy ป้องกัน SQL injection:

```bash
curl "http://localhost:8000/api/v1/opportunities?status='; DROP TABLE opportunities; --"
```

ควรได้ error หรือ empty result, ไม่ใช่ drop table

### 2. XSS

ทดสอบ input validation:

```bash
curl -X POST http://localhost:8000/api/v1/contacts \
  -H "Content-Type: application/json" \
  -d '{"name": "<script>alert(1)</script>", "email": "test@example.com"}'
```

### 3. Rate Limiting

ทดสอบว่า rate limiting ทำงาน:

```bash
for i in {1..100}; do
  curl http://localhost:8000/api/v1/opportunities &
done
```

## ✅ Pre-Deployment Checklist

### Environment

- [ ] `.env` file configured
- [ ] All API keys valid
- [ ] Database URL correct
- [ ] Redis URL correct

### Database

- [ ] Migrations run successfully
- [ ] All tables created
- [ ] Indexes created
- [ ] Backup configured

### Services

- [ ] Backend starts without errors
- [ ] Celery worker running
- [ ] Redis accessible
- [ ] Database accessible

### Tests

- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] Manual testing complete
- [ ] Performance acceptable

### Integrations

- [ ] Telegram bot working (if configured)
- [ ] Google Workspace working (if configured)
- [ ] Obsidian sync working (if configured)
- [ ] Scrapers working

### Monitoring

- [ ] Health checks responding
- [ ] Logs accessible
- [ ] Metrics tracking
- [ ] Alerts configured

### Security

- [ ] API keys not in code
- [ ] Environment variables secure
- [ ] CORS configured
- [ ] Rate limiting enabled

## 🎉 Success Criteria

ระบบพร้อมใช้งานเมื่อ:

1. ✅ All tests pass (100% pass rate)
2. ✅ Health check returns "ready"
3. ✅ API endpoints respond correctly
4. ✅ Database operations work
5. ✅ Event bus processes events
6. ✅ Agents execute successfully
7. ✅ Obsidian sync works
8. ✅ No critical errors in logs
9. ✅ Performance meets requirements
10. ✅ Security checks pass

## 📞 Troubleshooting

### Tests Failing

1. ตรวจสอบ database connection
2. ตรวจสอบ Redis connection
3. ตรวจสอบ environment variables
4. ดู error messages ใน logs
5. Run tests individually

### Performance Issues

1. ตรวจสอบ database indexes
2. ตรวจสอบ slow queries
3. เพิ่ม caching
4. Optimize agent logic
5. Scale services

### Integration Issues

1. ตรวจสอบ API keys
2. ตรวจสอบ network connectivity
3. ตรวจสอบ rate limits
4. ดู external service status
5. Check logs for errors

## 📚 Resources

- [pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [SQLAlchemy Testing](https://docs.sqlalchemy.org/en/14/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites)
- [Locust Documentation](https://docs.locust.io/)

# 🚀 PHASE 2: SYSTEM IMPROVEMENTS

**วันที่:** 2026-04-26  
**สถานะ:** Phase 1 Complete ✅ → Starting Phase 2

---

## 📊 Current Status

### Phase 1 Complete ✅
- ✅ แก้ไข critical issues ทั้งหมด (7/7)
- ✅ Backend imports successfully
- ✅ Celery tasks working
- ✅ Database unified
- ✅ Security improved
- ✅ Skills accessible (25 skills)

**คะแนน:** 45/100 → 70/100 (+25)

---

## 🎯 Phase 2 Goals

เพิ่มคะแนนจาก 70/100 → 85/100 (+15)

### Focus Areas:
1. ✅ Integration Tests
2. ✅ Monitoring & Alerting
3. ✅ Documentation
4. ✅ Performance Optimization
5. ✅ Error Tracking

---

## 📝 Task List

### 1. Integration Tests (HIGH PRIORITY)

#### 1.1 Create Test Infrastructure
```python
# tests/integration/conftest.py
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.fixture
async def db_session():
    # Create test database session
    pass
```

#### 1.2 Test Critical Paths
- [ ] Opportunity creation → scoring → decision → draft
- [ ] Submission tracking → outcome → learning
- [ ] Contact management → relationship tracking
- [ ] Task creation → assignment → completion
- [ ] Cost tracking → budget alerts

#### 1.3 Test Graxia Integration
- [ ] Graxia enabled/disabled modes
- [ ] Swarm execution
- [ ] Approval workflow
- [ ] WebSocket streaming

---

### 2. Monitoring & Alerting (HIGH PRIORITY)

#### 2.1 Grafana Dashboards

**Dashboard 1: System Health**
```yaml
panels:
  - CPU Usage
  - Memory Usage
  - Disk Usage
  - Network I/O
  - Process Count
```

**Dashboard 2: Application Metrics**
```yaml
panels:
  - Request Rate
  - Response Time (p50, p95, p99)
  - Error Rate
  - Active Users
  - Database Connections
```

**Dashboard 3: Business Metrics**
```yaml
panels:
  - Opportunities Found
  - Opportunities Scored
  - Submissions Sent
  - Success Rate
  - Revenue Generated
```

**Dashboard 4: Celery Workers**
```yaml
panels:
  - Active Workers
  - Task Queue Depth
  - Task Success Rate
  - Task Duration
  - Failed Tasks
```

**Dashboard 5: LLM Costs**
```yaml
panels:
  - Daily Cost
  - Cost by Model
  - Token Usage
  - Request Count
  - Cost Trend
```

#### 2.2 Alertmanager Rules

```yaml
# deploy/monitoring/alertmanager/rules.yml
groups:
  - name: critical
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate detected"
          
      - alert: DatabaseDown
        expr: up{job="postgres"} == 0
        for: 1m
        labels:
          severity: critical
          
      - alert: RedisDown
        expr: up{job="redis"} == 0
        for: 1m
        labels:
          severity: critical
          
      - alert: WorkerDown
        expr: celery_workers_online == 0
        for: 5m
        labels:
          severity: critical
          
  - name: warning
    rules:
      - alert: HighResponseTime
        expr: histogram_quantile(0.95, http_request_duration_seconds) > 1
        for: 10m
        labels:
          severity: warning
          
      - alert: HighMemoryUsage
        expr: process_resident_memory_bytes > 1e9
        for: 10m
        labels:
          severity: warning
          
      - alert: CostThresholdExceeded
        expr: daily_llm_cost_usd > 2.0
        for: 1h
        labels:
          severity: warning
```

#### 2.3 Setup Scripts

```bash
# scripts/setup_monitoring.sh
#!/bin/bash

echo "Setting up monitoring..."

# Create Grafana dashboards
for dashboard in deploy/monitoring/grafana/dashboards/*.json; do
    curl -X POST http://admin:${GRAFANA_ADMIN_PASSWORD}@localhost:3000/api/dashboards/db \
        -H "Content-Type: application/json" \
        -d @$dashboard
done

# Configure Alertmanager
docker cp deploy/monitoring/alertmanager/rules.yml personal_os_alertmanager:/etc/alertmanager/
docker restart personal_os_alertmanager

echo "✅ Monitoring setup complete"
```

---

### 3. Documentation (MEDIUM PRIORITY)

#### 3.1 API Documentation
- [ ] Complete OpenAPI spec
- [ ] Add request/response examples
- [ ] Document authentication
- [ ] Document rate limits
- [ ] Add error codes reference

#### 3.2 Architecture Documentation
- [ ] System architecture diagram
- [ ] Data flow diagrams
- [ ] Component interaction diagrams
- [ ] Deployment architecture

#### 3.3 Operational Documentation
- [ ] Deployment guide
- [ ] Backup & restore procedures
- [ ] Troubleshooting guide
- [ ] Monitoring guide
- [ ] Security guide

#### 3.4 Developer Documentation
- [ ] Setup guide
- [ ] Development workflow
- [ ] Testing guide
- [ ] Contributing guide
- [ ] Code style guide

---

### 4. Performance Optimization (MEDIUM PRIORITY)

#### 4.1 Database Optimization

**Add Indexes:**
```sql
-- Opportunities
CREATE INDEX idx_opportunities_status ON opportunities(status);
CREATE INDEX idx_opportunities_score ON opportunities(total_score DESC);
CREATE INDEX idx_opportunities_deadline ON opportunities(deadline);
CREATE INDEX idx_opportunities_found_at ON opportunities(found_at DESC);

-- Submissions
CREATE INDEX idx_submissions_status ON submissions(status);
CREATE INDEX idx_submissions_opportunity ON submissions(opportunity_id);
CREATE INDEX idx_submissions_sent_at ON submissions(sent_at DESC);

-- Contacts
CREATE INDEX idx_contacts_email ON contacts(email);
CREATE INDEX idx_contacts_company ON contacts(company);
CREATE INDEX idx_contacts_last_contacted ON contacts(last_contacted_at DESC);

-- Tasks
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_priority ON tasks(priority);
CREATE INDEX idx_tasks_due_date ON tasks(due_date);
```

**Query Optimization:**
```python
# Use select_related and prefetch_related
opportunities = await db.execute(
    select(Opportunity)
    .options(selectinload(Opportunity.submissions))
    .where(Opportunity.status == "active")
    .order_by(Opportunity.total_score.desc())
    .limit(10)
)
```

#### 4.2 Caching Strategy

```python
# backend/app/core/cache.py
from functools import wraps
import redis.asyncio as aioredis
import json

redis_client = aioredis.from_url(settings.REDIS_URL)

def cache(ttl: int = 300):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}:{args}:{kwargs}"
            
            # Try cache first
            cached = await redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Cache result
            await redis_client.setex(
                cache_key,
                ttl,
                json.dumps(result)
            )
            
            return result
        return wrapper
    return decorator

# Usage
@cache(ttl=600)
async def get_opportunities_summary():
    # Expensive query
    pass
```

#### 4.3 Frontend Optimization

```typescript
// Lazy loading
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Opportunities = lazy(() => import('./pages/Opportunities'));

// Code splitting
<Suspense fallback={<Loading />}>
  <Routes>
    <Route path="/dashboard" element={<Dashboard />} />
    <Route path="/opportunities" element={<Opportunities />} />
  </Routes>
</Suspense>

// Image optimization
<img 
  src={imageUrl} 
  loading="lazy"
  srcSet={`${imageUrl}?w=400 400w, ${imageUrl}?w=800 800w`}
  sizes="(max-width: 768px) 400px, 800px"
/>
```

---

### 5. Error Tracking (MEDIUM PRIORITY)

#### 5.1 Setup Sentry

```python
# backend/app/main.py
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.APP_ENV,
        traces_sample_rate=0.1,
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
        ],
    )
```

#### 5.2 Structured Logging

```python
# backend/app/core/logging_config.py
import structlog

def setup_logging(level: str = "INFO"):
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

---

## 📈 Expected Improvements

### Performance
- 50% faster response times (caching)
- 30% reduction in database load (indexes)
- 40% smaller bundle size (code splitting)

### Reliability
- 99.9% uptime (monitoring + alerts)
- < 5 min MTTR (mean time to recovery)
- Zero data loss (backup testing)

### Developer Experience
- 80%+ test coverage
- Complete documentation
- Clear error messages
- Fast feedback loops

---

## 🎯 Success Metrics

### Phase 2 Complete When:
- [ ] Integration tests pass (80%+ coverage)
- [ ] Monitoring dashboards live
- [ ] Alerting configured and tested
- [ ] Documentation complete
- [ ] Performance benchmarks met
- [ ] Error tracking operational

**Target Score:** 85/100

---

## 📅 Timeline

### Week 1 (Current)
- [x] Phase 1: Fix critical issues
- [ ] Setup integration tests
- [ ] Create monitoring dashboards

### Week 2
- [ ] Configure alerting
- [ ] Add database indexes
- [ ] Implement caching

### Week 3
- [ ] Complete documentation
- [ ] Setup error tracking
- [ ] Performance testing

### Week 4
- [ ] Final verification
- [ ] Production deployment
- [ ] Post-deployment monitoring

---

## 🚀 Quick Start

### Run Integration Tests
```bash
make test-integration
```

### Setup Monitoring
```bash
bash scripts/setup_monitoring.sh
```

### Generate Documentation
```bash
make docs
```

### Run Performance Tests
```bash
make perf-test
```

---

**Next:** ผมจะเริ่มสร้าง integration tests และ monitoring dashboards

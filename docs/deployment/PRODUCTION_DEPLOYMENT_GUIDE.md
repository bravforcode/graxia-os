# 🚀 PRODUCTION DEPLOYMENT GUIDE — Graxia Intelligence OS

**Version:** 1.0  
**Last Updated:** 2026-05-07  
**Status:** Production Ready

---

## 📋 OVERVIEW

This guide provides step-by-step instructions for deploying all security remediation fixes to production. All 20 issues from the Ultra Project Audit have been resolved and are ready for deployment.

**Deployment Phases:**
- **Phase 1:** Emergency Security Fixes (2 Critical issues)
- **Phase 2:** High Priority Fixes (5 High/Medium issues)
- **Phase 3:** Medium & Low Priority Fixes (13 Medium/Low issues)

**Total Changes:**
- 16 files modified
- 31 files created
- 124+ test cases
- 5100+ lines of documentation

---

## ⚠️ PRE-DEPLOYMENT CHECKLIST

### Required Preparations

- [ ] **Backup Database**
  ```bash
  pg_dump -h $DB_HOST -U $DB_USER -d $DB_NAME > backup_$(date +%Y%m%d_%H%M%S).sql
  ```

- [ ] **Backup Redis**
  ```bash
  redis-cli --rdb backup_$(date +%Y%m%d_%H%M%S).rdb
  ```

- [ ] **Review All Changes**
  - [ ] Read Phase 1 Completion Report
  - [ ] Read Phase 2 Completion Report
  - [ ] Read Phase 3 Completion Report
  - [ ] Read Master Completion Report

- [ ] **Prepare Secrets**
  - [ ] Generate `SECRET_KEY` (32+ chars)
  - [ ] Generate `ENCRYPTION_KEY` (32+ chars)
  - [ ] Generate `POSTGRES_PASSWORD` (16+ chars)
  - [ ] Generate `ALERTMANAGER_WEBHOOK_SECRET` (32+ chars)

- [ ] **Schedule Deployment Window**
  - [ ] Choose low-traffic time
  - [ ] Notify team of deployment
  - [ ] Prepare rollback plan

- [ ] **Test on Staging**
  - [ ] Deploy to staging environment
  - [ ] Run full test suite
  - [ ] Verify all acceptance criteria
  - [ ] Benchmark query performance

---

## 🔐 STEP 1: GENERATE PRODUCTION SECRETS

### Generate Strong Secrets

```bash
# Generate SECRET_KEY (64 characters recommended for production)
openssl rand -hex 32

# Generate ENCRYPTION_KEY (64 characters recommended)
openssl rand -hex 32

# Generate POSTGRES_PASSWORD (32 characters recommended)
openssl rand -base64 32

# Generate ALERTMANAGER_WEBHOOK_SECRET (64 characters recommended)
openssl rand -hex 32

# Generate CSRF_SECRET (if not using SECRET_KEY)
openssl rand -hex 32

# Generate REDIS_PASSWORD
openssl rand -base64 32
```

### Update Production .env

```bash
# Security Secrets (REQUIRED)
SECRET_KEY=<generated-64-char-secret>
ENCRYPTION_KEY=<generated-64-char-secret>
POSTGRES_PASSWORD=<generated-32-char-password>
ALERTMANAGER_WEBHOOK_SECRET=<generated-64-char-secret>
CSRF_SECRET=<generated-64-char-secret>  # Optional, defaults to SECRET_KEY

# Redis Password
REDIS_PASSWORD=<generated-32-char-password>

# Update Redis URLs with password
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
CELERY_BROKER_URL=redis://:${REDIS_PASSWORD}@redis:6379/1
CELERY_RESULT_BACKEND=redis://:${REDIS_PASSWORD}@redis:6379/2

# Event Bus Configuration
EVENT_BUS_SHUTDOWN_TIMEOUT=30  # Seconds to wait for graceful shutdown
EVENT_BUS_MAX_QUEUE_SIZE=10000  # Maximum queue size for backpressure

# CSRF Configuration
CSRF_TOKEN_EXPIRY_HOURS=1  # CSRF token expiry time in hours

# Model Router Configuration
ROUTER_TASK_DEFAULTS="classification:cheap,low,300;triage:cheap,low,400;short_summary:cheap,low,450;analysis:mid,standard,800;short_draft:mid,standard,700;meeting_summary:mid,standard,800;proposal:high,high,1600;strategy:high,high,1200"
```

### Validate Secrets

```bash
# Run production configuration validation
cd backend
python scripts/validate_production_config.py

# Should output: ✅ Production configuration validation passed
```

---

## 📦 STEP 2: DEPLOY CODE CHANGES

### Pull Latest Code

```bash
# Pull latest code from repository
git fetch origin
git checkout main
git pull origin main

# Verify you're on the correct commit
git log -1 --oneline
```

### Build Docker Images

```bash
# Build backend image
docker build -t graxia-backend:latest -f backend/Dockerfile .

# Build frontend image (if applicable)
docker build -t graxia-frontend:latest -f frontend/Dockerfile .

# Verify build includes production validation
docker run --rm graxia-backend:latest python scripts/validate_production_config.py
```

### Update Docker Compose

```bash
# Update docker-compose.yml with new Redis config
# Ensure Redis uses config file instead of command-line password

# Verify docker-compose.yml
docker-compose config
```

---

## 🗄️ STEP 3: RUN DATABASE MIGRATIONS

### Backup Database (Again)

```bash
# Create backup before migration
pg_dump -h $DB_HOST -U $DB_USER -d $DB_NAME > backup_pre_migration_$(date +%Y%m%d_%H%M%S).sql
```

### Run Migration 018 (Database Indexes)

```bash
# Run migration with CONCURRENTLY option (zero downtime)
cd backend
alembic upgrade head

# Expected output:
# INFO  [alembic.runtime.migration] Running upgrade 017 -> 018, add_composite_query_indexes
# INFO  [alembic.runtime.migration] Migration complete
```

### Verify Indexes

```bash
# Run index verification script
python scripts/verify_indexes.py

# Expected output:
# ✅ All 17 indexes created successfully
# ✅ opportunities: 4 indexes
# ✅ contacts: 4 indexes
# ✅ email_threads: 4 indexes
# ✅ assistant_tasks: 5 indexes
```

### Benchmark Query Performance

```bash
# Run query benchmarks
python scripts/benchmark_queries.py --compare-baseline

# Expected output:
# ✅ Opportunities query: 45ms (was 220ms) - 80% improvement
# ✅ Contacts query: 28ms (was 145ms) - 81% improvement
# ✅ Email threads query: 38ms (was 175ms) - 78% improvement
# ✅ Assistant tasks query: 32ms (was 155ms) - 79% improvement
```

---

## 🚀 STEP 4: DEPLOY APPLICATION

### Stop Current Application

```bash
# Graceful shutdown (waits for event bus to finish processing)
docker-compose stop backend

# Wait for graceful shutdown (max 30 seconds)
# Monitor logs to verify graceful shutdown
docker-compose logs -f backend

# Expected output:
# EventBus: stop requested
# EventBus: waiting for 3 tasks to complete
# EventBus: processing loop stopped gracefully
```

### Start New Application

```bash
# Start backend with new code
docker-compose up -d backend

# Monitor startup logs
docker-compose logs -f backend

# Expected output:
# INFO: Application startup complete
# INFO: Uvicorn running on http://0.0.0.0:8000
```

### Verify Startup

```bash
# Check health endpoint
curl http://localhost:8000/health

# Expected output:
# {"status": "healthy"}

# Check secrets validation
# Application should start successfully (no RuntimeError)
```

---

## ✅ STEP 5: VERIFY DEPLOYMENT

### Run Verification Scripts

```bash
cd backend

# 1. Verify secrets validation
python scripts/verify_secrets_validation.py
# Expected: ✅ All secrets validated successfully

# 2. Verify graceful shutdown
python scripts/verify_graceful_shutdown.py
# Expected: ✅ Graceful shutdown working correctly

# 3. Verify database indexes
python scripts/verify_indexes.py
# Expected: ✅ All 17 indexes created successfully

# 4. Benchmark query performance
python scripts/benchmark_queries.py
# Expected: ✅ All queries < 50ms P95
```

### Run Test Suite

```bash
# Run full test suite
cd backend
python -m pytest tests/ -v

# Expected: All tests pass (124+ tests)
```

### Verify Security Fixes

#### 1. CSRF Protection

```bash
# Test CSRF token validation
curl -X POST http://localhost:8000/api/v1/opportunities \
  -H "Authorization: Bearer <valid-token>" \
  -d '{"title": "Test"}'

# Expected: 403 CSRF token missing
```

#### 2. Webhook HMAC Signature

```bash
# Test webhook without signature
curl -X POST http://localhost:8000/api/v1/integrations/alerts/telegram \
  -H "Content-Type: application/json" \
  -d '{"alert": "test"}'

# Expected: 401 Unauthorized

# Test webhook with valid signature
python scripts/test_webhook_signature.py

# Expected: 200 OK
```

#### 3. Secrets Validation

```bash
# Verify application won't start without secrets
# (Already verified during startup)

# Check logs for secrets validation
docker-compose logs backend | grep "secrets"

# Expected: No errors about missing secrets
```

#### 4. Graceful Shutdown

```bash
# Test graceful shutdown
docker-compose stop backend

# Monitor logs
docker-compose logs backend | grep "EventBus"

# Expected:
# EventBus: stop requested
# EventBus: waiting for X tasks to complete
# EventBus: processing loop stopped gracefully
```

#### 5. Event Bus Queue Limits

```bash
# Check event bus metrics
curl http://localhost:8000/api/v1/metrics/event-bus

# Expected:
# {
#   "queue_size": <number>,
#   "max_queue_size": 10000,
#   "queue_full_count": 0,
#   "dropped_events": 0,
#   "queue_utilization_percent": <number>
# }
```

#### 6. CSRF Token Expiry

```bash
# Generate CSRF token
curl -X GET http://localhost:8000/api/v1/auth/csrf-token \
  -H "Cookie: access_token=<valid-token>"

# Wait 1 hour + 1 minute

# Try to use expired token
curl -X POST http://localhost:8000/api/v1/opportunities \
  -H "Authorization: Bearer <valid-token>" \
  -H "X-CSRF-Token: <expired-token>" \
  -d '{"title": "Test"}'

# Expected: 403 CSRF token forged (expired)
```

---

## 📊 STEP 6: MONITOR PRODUCTION

### Key Metrics to Monitor

#### 1. Query Performance

```bash
# Monitor slow queries
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
WHERE mean_exec_time > 50
ORDER BY mean_exec_time DESC
LIMIT 10;
"

# Expected: No queries > 50ms for filtered operations
```

#### 2. Event Bus Metrics

```bash
# Monitor event bus queue depth
curl http://localhost:8000/api/v1/metrics/event-bus

# Watch for:
# - queue_size < 1000 (normal load)
# - queue_full_count = 0 (no backpressure)
# - dropped_events = 0 (no events dropped)
```

#### 3. CSRF Violations

```bash
# Monitor CSRF violations
docker-compose logs backend | grep "csrf_violation"

# Watch for:
# - missing_token: Legitimate (first request)
# - token_mismatch: Suspicious (potential attack)
# - forged_token: Critical (attack attempt)
```

#### 4. Webhook Authentication

```bash
# Monitor webhook authentication
docker-compose logs backend | grep "webhook"

# Watch for:
# - Successful HMAC signature verifications
# - Failed authentication attempts (potential attacks)
```

#### 5. Secrets Validation

```bash
# Monitor secrets validation errors
docker-compose logs backend | grep "secrets"

# Expected: No errors (all secrets valid)
```

### Set Up Alerts

```yaml
# Alertmanager rules (alertmanager.yml)
groups:
  - name: graxia_security
    rules:
      # Alert on CSRF violations
      - alert: HighCSRFViolations
        expr: rate(csrf_violations_total[5m]) > 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High CSRF violation rate"
          description: "CSRF violations > 10/min for 5 minutes"

      # Alert on webhook authentication failures
      - alert: WebhookAuthFailures
        expr: rate(webhook_auth_failures_total[5m]) > 5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High webhook auth failure rate"
          description: "Webhook auth failures > 5/min for 5 minutes"

      # Alert on event bus queue depth
      - alert: EventBusQueueHigh
        expr: event_bus_queue_size > 5000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Event bus queue depth high"
          description: "Event bus queue > 5000 events for 5 minutes"

      # Alert on slow queries
      - alert: SlowQueries
        expr: pg_stat_statements_mean_exec_time_seconds > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Slow database queries detected"
          description: "Queries > 100ms for 5 minutes"
```

---

## 🔄 ROLLBACK PLAN

### If Issues Occur

#### 1. Rollback Code

```bash
# Stop current application
docker-compose stop backend

# Revert to previous version
git checkout <previous-commit>

# Rebuild and restart
docker build -t graxia-backend:rollback -f backend/Dockerfile .
docker-compose up -d backend
```

#### 2. Rollback Database Migration

```bash
# Rollback migration 018 (if needed)
cd backend
alembic downgrade -1

# Verify rollback
python scripts/verify_indexes.py
# Expected: Indexes removed
```

#### 3. Restore Database (Last Resort)

```bash
# Stop application
docker-compose stop backend

# Restore from backup
psql -h $DB_HOST -U $DB_USER -d $DB_NAME < backup_pre_migration_<timestamp>.sql

# Restart application
docker-compose up -d backend
```

#### 4. Restore Redis (If Needed)

```bash
# Stop Redis
docker-compose stop redis

# Restore from backup
cp backup_<timestamp>.rdb /data/dump.rdb

# Restart Redis
docker-compose up -d redis
```

---

## 📝 POST-DEPLOYMENT CHECKLIST

### Immediate Actions (First Hour)

- [ ] **Verify Health Endpoint**
  ```bash
  curl http://localhost:8000/health
  # Expected: {"status": "healthy"}
  ```

- [ ] **Check Application Logs**
  ```bash
  docker-compose logs -f backend
  # Watch for errors or warnings
  ```

- [ ] **Monitor Query Performance**
  ```bash
  python scripts/benchmark_queries.py
  # Verify all queries < 50ms P95
  ```

- [ ] **Check Event Bus Metrics**
  ```bash
  curl http://localhost:8000/api/v1/metrics/event-bus
  # Verify queue_size < 1000
  ```

- [ ] **Verify CSRF Protection**
  ```bash
  # Test CSRF token validation
  curl -X POST http://localhost:8000/api/v1/opportunities \
    -H "Authorization: Bearer <valid-token>" \
    -d '{"title": "Test"}'
  # Expected: 403 CSRF token missing
  ```

### Short-term Actions (First Day)

- [ ] **Monitor CSRF Violations**
  ```bash
  docker-compose logs backend | grep "csrf_violation" | wc -l
  # Expected: Low count (< 100)
  ```

- [ ] **Monitor Webhook Authentication**
  ```bash
  docker-compose logs backend | grep "webhook" | grep "401"
  # Expected: No unauthorized attempts
  ```

- [ ] **Check Database Performance**
  ```bash
  psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "
  SELECT query, mean_exec_time, calls
  FROM pg_stat_statements
  WHERE mean_exec_time > 50
  ORDER BY mean_exec_time DESC
  LIMIT 10;
  "
  # Expected: No queries > 50ms for filtered operations
  ```

- [ ] **Verify Graceful Shutdown**
  ```bash
  # Trigger deployment or restart
  docker-compose restart backend
  
  # Check logs
  docker-compose logs backend | grep "EventBus"
  # Expected: "processing loop stopped gracefully"
  ```

### Long-term Actions (First Week)

- [ ] **Review Metrics Dashboard**
  - Query performance trends
  - Event bus queue depth trends
  - CSRF violation trends
  - Webhook authentication trends

- [ ] **Conduct Post-Mortem**
  - Document any issues encountered
  - Update deployment guide based on experience
  - Share lessons learned with team

- [ ] **Update Documentation**
  - Update runbooks with production experience
  - Document any edge cases discovered
  - Update troubleshooting guides

---

## 🆘 TROUBLESHOOTING

### Issue 1: Application Won't Start (Secrets Validation)

**Symptoms:**
- Application exits with RuntimeError
- Error message: "Required secrets not configured"

**Diagnosis:**
```bash
# Check .env file
cat .env | grep -E "SECRET_KEY|ENCRYPTION_KEY|POSTGRES_PASSWORD"

# Run validation script
python scripts/validate_production_config.py
```

**Solution:**
```bash
# Generate missing secrets
openssl rand -hex 32  # For SECRET_KEY
openssl rand -hex 32  # For ENCRYPTION_KEY
openssl rand -base64 32  # For POSTGRES_PASSWORD

# Add to .env
echo "SECRET_KEY=<generated-secret>" >> .env
echo "ENCRYPTION_KEY=<generated-secret>" >> .env
echo "POSTGRES_PASSWORD=<generated-password>" >> .env

# Restart application
docker-compose up -d backend
```

---

### Issue 2: Database Migration Fails

**Symptoms:**
- Migration hangs or times out
- Error message: "could not obtain lock"

**Diagnosis:**
```bash
# Check for long-running queries
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "
SELECT pid, now() - pg_stat_activity.query_start AS duration, query
FROM pg_stat_activity
WHERE state = 'active'
ORDER BY duration DESC;
"
```

**Solution:**
```bash
# Option 1: Wait for queries to complete
# (Recommended for production)

# Option 2: Cancel long-running queries (if safe)
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "
SELECT pg_cancel_backend(<pid>);
"

# Option 3: Rollback and retry during low-traffic window
alembic downgrade -1
# Wait for low-traffic window
alembic upgrade head
```

---

### Issue 3: High CSRF Violation Rate

**Symptoms:**
- Many 403 CSRF token errors in logs
- Users unable to submit forms

**Diagnosis:**
```bash
# Check CSRF violation reasons
docker-compose logs backend | grep "csrf_violation" | grep -o '"reason":"[^"]*"' | sort | uniq -c

# Expected reasons:
# - missing_token: Legitimate (first request)
# - token_mismatch: Suspicious (potential attack)
# - forged_token: Critical (attack attempt)
```

**Solution:**
```bash
# If mostly "missing_token":
# - Normal for first requests
# - Ensure frontend sends CSRF token in X-CSRF-Token header

# If mostly "token_mismatch":
# - Check for clock skew between servers
# - Verify CSRF_SECRET is consistent across instances

# If mostly "forged_token":
# - Potential attack - investigate source IPs
# - Consider rate limiting or blocking IPs
```

---

### Issue 4: Event Bus Queue Growing

**Symptoms:**
- Event bus queue size > 5000
- Slow event processing
- Potential memory issues

**Diagnosis:**
```bash
# Check event bus metrics
curl http://localhost:8000/api/v1/metrics/event-bus

# Check event processing rate
docker-compose logs backend | grep "EventBus: handler" | tail -100
```

**Solution:**
```bash
# Option 1: Increase processing capacity
# - Scale up backend instances
# - Increase worker threads

# Option 2: Reduce event emission rate
# - Throttle event sources
# - Batch events

# Option 3: Increase queue size (if memory allows)
# Update .env:
EVENT_BUS_MAX_QUEUE_SIZE=20000

# Restart application
docker-compose restart backend
```

---

### Issue 5: Slow Queries After Migration

**Symptoms:**
- Queries still slow (> 50ms) after adding indexes
- Database CPU high

**Diagnosis:**
```bash
# Check if indexes are being used
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "
SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY idx_scan DESC;
"

# Check query plans
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "
EXPLAIN ANALYZE
SELECT * FROM opportunities WHERE user_id = 1 AND status = 'pending';
"
```

**Solution:**
```bash
# Option 1: Analyze tables (update statistics)
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "
ANALYZE opportunities;
ANALYZE contacts;
ANALYZE email_threads;
ANALYZE assistant_tasks;
"

# Option 2: Reindex (if indexes corrupted)
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "
REINDEX TABLE opportunities;
REINDEX TABLE contacts;
REINDEX TABLE email_threads;
REINDEX TABLE assistant_tasks;
"

# Option 3: Check for missing indexes
python scripts/verify_indexes.py
```

---

## 📞 SUPPORT CONTACTS

### Escalation Path

**Level 1: On-Call Engineer**
- Response Time: < 15 minutes
- Contact: [On-call rotation]

**Level 2: Tech Lead**
- Response Time: < 1 hour
- Contact: [Tech lead contact]

**Level 3: CTO**
- Response Time: < 4 hours
- Contact: [CTO contact]

### Emergency Procedures

**Critical Issues (System Down):**
1. Contact on-call engineer immediately
2. Execute rollback plan if needed
3. Escalate to tech lead if not resolved in 30 minutes

**High Priority Issues (Degraded Performance):**
1. Contact on-call engineer
2. Investigate and diagnose
3. Escalate to tech lead if not resolved in 2 hours

**Medium Priority Issues (Non-Critical):**
1. Create incident ticket
2. Investigate during business hours
3. Escalate if needed

---

## ✅ DEPLOYMENT SIGN-OFF

**Pre-Deployment:**
- [ ] All pre-deployment checks complete
- [ ] Secrets generated and validated
- [ ] Staging deployment successful
- [ ] Team notified of deployment window

**Deployment:**
- [ ] Code deployed successfully
- [ ] Database migrations complete
- [ ] Application started successfully
- [ ] All verification scripts pass

**Post-Deployment:**
- [ ] Health checks passing
- [ ] Metrics within normal ranges
- [ ] No critical errors in logs
- [ ] Team notified of successful deployment

**Sign-Off:**
- **Deployed by:** _________________
- **Reviewed by:** _________________
- **Approved by:** _________________
- **Date:** _________________

---

## 🎉 CONCLUSION

This deployment guide provides comprehensive instructions for deploying all security remediation fixes to production. Follow each step carefully and verify all acceptance criteria before proceeding to the next step.

**Key Points:**
- ✅ All 20 issues resolved and ready for deployment
- ✅ Comprehensive verification scripts provided
- ✅ Rollback plan documented
- ✅ Monitoring and alerting configured
- ✅ Troubleshooting guide included

**Production Ready:** ✅ **YES**

**Good luck with the deployment! 🚀**


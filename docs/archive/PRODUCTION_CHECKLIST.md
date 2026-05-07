# Graxia OS Production Deployment Checklist

## Pre-Deployment Verification

### Code Quality
- [ ] All unit tests passing (`pytest tests/unit/ -v`)
- [ ] All integration tests passing (`pytest tests/integration/ -v`)
- [ ] Security tests passing (`pytest tests/security/ -v`)
- [ ] Code coverage > 80% (`pytest --cov=app --cov-report=term-missing`)
- [ ] No critical linting errors (`ruff check app/`)
- [ ] Type checking passed (`mypy app/ --ignore-missing-imports`)

### Database
- [ ] Database migrations reviewed (`alembic history`)
- [ ] Migration tested on staging (`alembic upgrade head`)
- [ ] Rollback plan documented (`alembic downgrade -1`)
- [ ] Database backup completed (`python scripts/backup_database.py pg_dump`)
- [ ] Connection pool settings verified

### Security
- [ ] `SECRET_KEY` rotated (min 32 characters, random)
- [ ] `INTERNAL_API_KEY` rotated
- [ ] `SENTRY_DSN` configured (production project)
- [ ] SSL certificates valid (expiry > 30 days)
- [ ] CORS origins restricted to production domains only
- [ ] Rate limiting enabled

### External Services
- [ ] Stripe keys configured (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`)
- [ ] Resend API key configured (`RESEND_API_KEY`)
- [ ] OpenClaw API key configured (`OPENCLAW_API_KEY`)
- [ ] Obsidian REST token configured (`OBSIDIAN_REST_TOKEN`)
- [ ] Telegram bot token configured (`TELEGRAM_BOT_TOKEN`)

### Monitoring
- [ ] Sentry project configured
- [ ] Health check endpoints responding (`/health`, `/system/stats`)
- [ ] Log aggregation configured
- [ ] Alert thresholds set

---

## Deployment Steps

### Step 1: Pre-Deploy (Local)
```bash
# 1. Verify tests
pytest tests/ -v --tb=short

# 2. Check migrations
alembic current
alembic history --verbose

# 3. Build Docker image locally
docker build -t graxia-api:test .
docker run -p 8000:8000 graxia-api:test

# 4. Test locally
curl http://localhost:8000/health
```

### Step 2: Secrets Verification (Fly.io)
```bash
# Verify all secrets are set
fly secrets list --app graxia-api

# Required secrets checklist:
# - DATABASE_URL
# - REDIS_URL
# - SECRET_KEY
# - STRIPE_SECRET_KEY
# - STRIPE_WEBHOOK_SECRET
# - RESEND_API_KEY
# - OPENCLAW_API_KEY
# - SENTRY_DSN (optional but recommended)
```

### Step 3: Deploy to Fly.io
```bash
# Deploy with rolling strategy
fly deploy --app graxia-api --strategy rolling

# Monitor deployment
fly status --app graxia-api --watch
```

### Step 4: Post-Deploy Verification
```bash
# 1. Health check
curl https://graxia-api.fly.dev/health

# 2. System stats (requires auth)
curl -H "Authorization: Bearer <token>" https://graxia-api.fly.dev/system/stats

# 3. Check logs
fly logs --app graxia-api

# 4. Database connectivity
fly ssh console --app graxia-api -C "python -c 'from app.database import check_db_health; import asyncio; print(asyncio.run(check_db_health()))'"

# 5. Redis connectivity
fly ssh console --app graxia-api -C "python -c 'from app.core.redis_pool import ping_redis; import asyncio; print(asyncio.run(ping_redis()))'"
```

### Step 5: Database Migrations (if needed)
```bash
# Check current version
fly ssh console --app graxia-api -C "python -m alembic current"

# Apply migrations
fly ssh console --app graxia-api -C "python -m alembic upgrade head"

# Verify
fly ssh console --app graxia-api -C "python -m alembic current"
```

### Step 6: Integration Testing
```bash
# Test Stripe webhook (test mode)
curl -X POST https://graxia-api.fly.dev/billing/webhook \
  -H "Stripe-Signature: <test-signature>" \
  -d '<test-payload>'

# Test email service
python -c "from app.core.email import send_email; import asyncio; asyncio.run(send_email('test@example.com', 'Test', '<p>Test</p>'))"

# Test Obsidian sync
python -c "from app.agents.obsidian_sync import obsidian_sync_agent; import asyncio; asyncio.run(obsidian_sync_agent.test_obsidian_connection())"
```

### Step 7: Monitoring Setup
```bash
# Verify Sentry is receiving events
# (trigger a test error and verify in Sentry dashboard)

# Check Fly.io monitoring
curl https://api.fly.io/prometheus/.../graxia-api

# Verify Telegram alerts
python -c "from app.core.telegram import send_message; import asyncio; asyncio.run(send_message('🚀 Production deployment successful'))"
```

---

## Post-Deployment Monitoring (24 hours)

### Hour 1: Immediate
- [ ] Error rates normal (< 0.1%)
- [ ] Response times normal (< 200ms p95)
- [ ] All health checks passing
- [ ] No critical alerts

### Hour 6: Stabilization
- [ ] Database connection pool stable
- [ ] Redis connections healthy
- [ ] Memory usage stable
- [ ] No memory leaks detected

### Hour 24: Validation
- [ ] User reports (no complaints)
- [ ] All scheduled tasks running
- [ ] Backup verification successful
- [ ] Sentry issues triaged

---

## Rollback Criteria

### Automatic Rollback Triggers
- Error rate > 5%
- Response time > 1000ms p95
- Health check failures > 3 consecutive
- Database connection pool exhaustion

### Manual Rollback Procedure
```bash
# 1. Identify previous version
fly releases list --app graxia-api

# 2. Rollback
fly deploy --app graxia-api --image graxia-api:deployment-<PREVIOUS_VERSION>

# 3. Verify rollback
fly status --app graxia-api
curl https://graxia-api.fly.dev/health

# 4. Notify team
# Post in #incident-response channel
```

---

## Sign-off

### Deployed By
**Name**: _________________  
**Date**: _________________  
**Time**: _________________

### Verified By
**Name**: _________________  
**Date**: _________________  
**Time**: _________________

### Approved By
**Name**: _________________  
**Date**: _________________  
**Signature**: _________________

---

## Post-Deployment Notes

**Issues Encountered**:  
___________________________________________________________

**Resolution**:  
___________________________________________________________

**Lessons Learned**:  
___________________________________________________________

**Follow-up Actions**:  
___________________________________________________________

---

**Document Version**: 1.0  
**Last Updated**: 2026-05-06

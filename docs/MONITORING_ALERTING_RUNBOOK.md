# Monitoring & Alerting Runbook

> Monitoring infrastructure, metric thresholds, alert rules, and dashboard references for production dry-run.

## Monitoring Stack

| Component | Purpose | Endpoint | Status in Dry-Run |
|-----------|---------|----------|-------------------|
| **Health endpoint** | Basic service health | `GET /health` | ✅ Active |
| **Readiness endpoint** | Subsystem status | `GET /api/v1/health/readiness` | ✅ Active |
| **Metrics endpoint** | Prometheus scraping | `GET /metrics` | ✅ Active |
| **Sentry** | Error tracking | External | ⚠️ Requires DSN config |
| **Telegram** | Real-time alerts | External | ⚠️ Requires bot token |
| **Alertmanager** | Alert routing | Internal | ⚠️ Requires config |
| **Prometheus** | Metric collection | Internal | ⚠️ Requires setup |
| **Grafana** | Dashboards | Internal | ⚠️ Requires setup |

## Health Check Endpoints

```bash
# Basic health
curl -s http://localhost:8000/health

# Full readiness (requires auth)
curl -s -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/health/readiness

# Staging readiness
curl -s -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/health/readiness/staging

# Production readiness
curl -s -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/health/readiness/production
```

## Metric Thresholds

| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| Backend response time (p95) | > 500ms | > 2s | Check DB queries, Redis |
| Database connections | > 80% pool | > 95% pool | Scale up, check leaks |
| Memory usage | > 70% | > 85% | Restart, check leaks |
| CPU usage | > 70% | > 90% | Scale up, optimize |
| Disk usage | > 80% | > 90% | Clean up, extend volume |
| Rate limit breaches | > 10/min | > 50/min | Investigate abuse |
| Failed auth attempts | > 5/min | > 20/min | Check for brute force |
| 5xx errors | > 1% | > 5% | Check error logs |
| 4xx errors | > 5% | > 10% | Check client behavior |
| Queue depth (Celery) | > 100 | > 500 | Scale workers |

## Alert Rules

### Critical Alerts (SEV-1/SEV-2)

| Alert | Condition | Channel | Response |
|-------|-----------|---------|----------|
| `BackendDown` | Health endpoint returns != 200 for 30s | Telegram + Sentry | Immediate |
| `DatabaseDown` | Readiness shows DB unhealthy | Telegram | Immediate |
| `AuthBroken` | 401 rate > 20/min | Telegram | Immediate |
| `RateLimitExhausted` | Rate limit breaches > 50/min | Telegram | Investigate |
| `MemoryCritical` | Memory > 85% | Telegram | Restart/scale |
| `DiskFull` | Disk > 90% | Telegram | Clean up |

### Warning Alerts (SEV-3/SEV-4)

| Alert | Condition | Channel | Response |
|-------|-----------|---------|----------|
| `SlowResponses` | p95 > 1s for 5min | Telegram | Investigate |
| `HighErrorRate` | 5xx > 2% for 5min | Telegram | Investigate |
| `MigrationPending` | Alembic head != expected | Telegram | Review |
| `SecretExpiring` | Secret age > 80 days | Telegram | Rotate |

## Grafana Dashboards

### Dashboard: Backend Overview
- Request rate (rps)
- Response time (p50, p95, p99)
- Error rate by status code
- Database query time
- Redis command rate

### Dashboard: Security
- Rate limit breaches by route
- Failed auth attempts by IP
- Permission denial rate
- Org boundary violations
- Audit event rate by severity

### Dashboard: Business
- Active users
- API usage by endpoint group
- Daily active organizations
- Workflow execution count

## Prometheus Metrics

### Custom Metrics (from `app.core.monitoring`)

| Metric | Type | Labels |
|--------|------|--------|
| `http_requests_total` | Counter | method, endpoint, status |
| `http_request_duration_seconds` | Histogram | method, endpoint |
| `db_query_duration_seconds` | Histogram | operation, table |
| `rate_limit_exceeded_total` | Counter | route, ip |
| `auth_failure_total` | Counter | reason |
| `audit_events_total` | Counter | event_type, severity |

## Alertmanager Configuration

```yaml
# config/alertmanager.yml
route:
  receiver: 'telegram'
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h

receivers:
  - name: 'telegram'
    webhook_configs:
      - url: 'http://localhost:8000/api/v1/integrations/alerts/telegram'
        send_resolved: true
```

## Logging

### Log Levels by Environment

| Environment | Backend | Celery | Frontend |
|-------------|---------|--------|----------|
| Production | INFO | INFO | ERROR |
| Staging | DEBUG | INFO | WARN |
| Development | DEBUG | DEBUG | DEBUG |

### Log Format (Structured JSON)

```json
{
  "timestamp": "2026-05-20T10:30:00Z",
  "level": "ERROR",
  "logger": "app.api.health",
  "request_id": "req_abc123",
  "correlation_id": "cor_xyz789",
  "message": "Database connectivity failed",
  "extra": {"db_host": "localhost", "db_port": 5432}
}
```

### Log Retention

| Environment | Retention | Storage |
|-------------|-----------|---------|
| Production | 30 days | Docker volume + external |
| Staging | 7 days | Docker volume |
| Development | 3 days | Local filesystem |

## Dry-Run Monitoring Validation

```bash
# 1. Verify health endpoint
curl -s http://localhost:8000/health | python -m json.tool

# 2. Verify readiness endpoint
curl -s -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/health/readiness | python -m json.tool

# 3. Verify metrics endpoint
curl -s http://localhost:8000/metrics | head -30

# 4. Verify Sentry (if configured)
# Trigger a test error:
curl -s http://localhost:8000/api/v1/system/test-error 2>/dev/null || true

# 5. Check backend logs
docker compose logs backend --tail=20

# 6. Verify Telegram alert (if configured)
# Trigger a test alert via health check failure simulation
```

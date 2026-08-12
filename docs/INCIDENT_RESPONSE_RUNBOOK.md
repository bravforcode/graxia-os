# Incident Response Runbook

> Structured procedures for detecting, responding to, and recovering from production incidents.

## Severity Levels

| Level | Definition | Response Time | Examples |
|-------|-----------|---------------|---------|
| **SEV-1** | Complete service outage | < 15 minutes | Database down, API unresponsive, auth broken |
| **SEV-2** | Major feature degradation | < 30 minutes | Payment failures, email not sending, rate limiting broken |
| **SEV-3** | Minor feature degradation | < 4 hours | UI glitch, slow page load, non-critical endpoint down |
| **SEV-4** | Low impact / cosmetic | < 24 hours | Incorrect label, typo, minor UI inconsistency |

## Detection

### Automated Detection

1. **Health endpoint monitoring** — `GET /health` must return 200
2. **Readiness monitoring** — `GET /api/v1/health/readiness` shows subsystem status
3. **Metrics endpoint** — `GET /metrics` for Prometheus scraping
4. **Sentry alerts** — Error tracking with configurable thresholds
5. **Telegram alerts** — Real-time notifications for blocked/error states
6. **Rate limit alerts** — Sudden rate limit threshold breaches

### Manual Detection

- Operator dashboard review
- User-reported issues
- Audit log review for unusual patterns
- Database query performance anomalies

## Response Procedure

### Step 1: Triage (First 5 minutes)

```
1. Confirm the incident is real (not a false alarm)
2. Determine severity level
3. Check if it's a known issue (search runbooks)
4. Assign incident commander
```

### Step 2: Containment

```
1. If live provider issue: verify ALLOW_LIVE_* gates are still false
2. If database issue: verify connection, run health check
3. If auth issue: check SECRET_KEY, JWT configuration
4. If rate limiting issue: check Redis, rate limit config
5. If safe error issue: check exception handlers
```

### Step 3: Diagnosis

Check these in order:

```bash
# 1. Health endpoint
curl -s http://localhost:8000/health | python -m json.tool

# 2. Readiness endpoint
curl -s http://localhost:8000/api/v1/health/readiness | python -m json.tool

# 3. Backend logs
docker compose logs backend --tail=100

# 4. Database connectivity
docker compose exec db pg_isready -U graxia

# 5. Redis connectivity
docker compose exec redis redis-cli ping

# 6. Recent errors
docker compose logs backend --tail=200 | grep -i "error\|exception\|traceback"

# 7. Audit logs
curl -s -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/v1/admin/audit-logs?limit=50&severity=ERROR" | python -m json.tool

# 8. Security audit events
curl -s -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/v1/admin/audit-logs?limit=50&category=security" | python -m json.tool
```

### Step 4: Resolution

| Issue | Action |
|-------|--------|
| Database down | Restart DB container, verify connection, check disk space |
| Auth broken | Verify SECRET_KEY, JWT config, restart backend |
| Rate limiting broken | Check Redis, reset rate limit state, restart rate limiter |
| API returning 500s | Check exception handlers, verify no stack trace leak |
| Migration issue | Verify Alembic head, downgrade if needed |
| Live provider blocked | Verify ALLOW_LIVE_* flags, check provider credentials |
| Audit not logging | Check audit service, database connectivity for audit table |

### Step 5: Recovery

1. Apply fix (rollback or hotfix)
2. Verify fix via health/readiness endpoints
3. Verify fix via test suite
4. Monitor for 15 minutes post-fix
5. Declare incident resolved

### Step 6: Post-Mortem (Within 24 hours)

1. Document timeline of events
2. Identify root cause
3. List contributing factors
4. Define corrective actions
5. Assign owners for each action
6. Schedule follow-up review

## Communication Templates

### Incident Started

```
INCIDENT: {SEVERITY} - {BRIEF_DESCRIPTION}
Time: {TIMESTAMP}
Impact: {WHAT_IS_AFFECTED}
Status: INVESTIGATING
Commander: {NAME}
```

### Incident Update

```
INCIDENT: {SEVERITY} - {BRIEF_DESCRIPTION}
Time: {TIMESTAMP}
Status: {INVESTIGATING|MITIGATING|RESOLVED}
Progress: {WHAT_HAS_BEEN_DONE}
Next steps: {NEXT_ACTIONS}
```

### Incident Resolved

```
INCIDENT: {SEVERITY} - {BRIEF_DESCRIPTION}
Time: {TIMESTAMP}
Status: RESOLVED
Root cause: {ROOT_CAUSE}
Fix applied: {FIX}
Post-mortem scheduled: {DATE_TIME}
```

## Escalation Path

| Level | Contact | Method | Response Time |
|-------|---------|--------|---------------|
| L1 (Operator) | Telegram | Instant | < 15 min |
| L2 (Developer) | Telegram + Phone | < 1 hour | < 30 min |
| L3 (Architect) | Phone | < 2 hours | < 1 hour |

## Post-Incident Review Checklist

- [ ] Timeline documented
- [ ] Root cause identified
- [ ] All affected users notified
- [ ] Data loss assessed (if any)
- [ ] Fix applied and verified
- [ ] Monitoring improved to detect recurrence
- [ ] Runbook updated with new procedures
- [ ] Security audit events reviewed for related incidents

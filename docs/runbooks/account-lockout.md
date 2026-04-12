# Runbook: Account Lockout

## What is happening?
Repeated failed logins crossed the lockout threshold for one or more accounts.

## Quick Diagnosis
```bash
docker compose -f docker-compose.prod.yml logs backend | tail -n 200
docker compose -f docker-compose.prod.yml exec redis redis-cli keys 'lockout:*'
```

## Resolution
1. Confirm the spike is not tied to an ongoing credential-stuffing event.
2. Review recent audit events in `/api/v1/admin/audit-logs`.
3. If a legitimate user is blocked, clear the lockout key only after verifying identity.
4. Keep the incident notes and source IPs for follow-up blocking.

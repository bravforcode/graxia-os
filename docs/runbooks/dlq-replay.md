# Runbook: DLQ Replay

## What is happening?
One or more Celery tasks exhausted retries and were moved to the dead-letter queue.

## Quick Diagnosis
```bash
curl -s https://app.example.com/api/v1/admin/dlq
docker compose -f docker-compose.prod.yml logs worker-critical | tail -n 200
```

## Resolution
1. Inspect the failing task type and exception.
2. Fix the upstream configuration or dependency problem first.
3. Replay the message from `/api/v1/admin/dlq/{message_id}/replay`.
4. If replay fails again, leave the message in DLQ and escalate.

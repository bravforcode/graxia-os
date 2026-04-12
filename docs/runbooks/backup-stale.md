# Runbook: Backup Stale

## What is happening?
The latest successful backup is older than the 25 hour alert threshold.

## Quick Diagnosis
```bash
docker compose -f docker-compose.prod.yml logs beat | tail -n 200
docker compose -f docker-compose.prod.yml logs worker-critical | tail -n 200
python backend/scripts/backup_database.py
```

## Resolution
1. Verify Redis, Postgres, and object-store credentials are valid.
2. Manually run the backup task and confirm checksum generation.
3. If backup encryption fails, restore the age key pair from the password manager.
4. Keep the alert open until a fresh verified backup is visible in metrics.

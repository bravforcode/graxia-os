# Disaster Recovery Runbook

**RPO target:** <24h  
**RTO target:** <4h

## 1. Provision and harden host
```bash
scp deploy/scripts/harden-vps.sh root@NEW_VPS:/tmp/harden-vps.sh
ssh root@NEW_VPS "bash /tmp/harden-vps.sh"
```

## 2. Sync stack and secrets
```bash
rsync -az . deploy@NEW_VPS:/opt/personal-os/
scp .env.production deploy@NEW_VPS:/opt/personal-os/.env.production
```

## 3. Start the platform
```bash
ssh deploy@NEW_VPS "cd /opt/personal-os && docker compose -f docker-compose.prod.yml up -d"
```

## 4. Restore data
```bash
ssh deploy@NEW_VPS "cd /opt/personal-os && python backend/scripts/restore_database.py"
```

## 5. Verify service
```bash
python deploy/scripts/smoke_test.py --target https://app.example.com
```

## Partial failures

### Missing age private key
1. Retrieve the key from the password manager entry for production backups.
2. If the key is unavailable, stop and escalate. Do not attempt partial restore with unverified data.

### Migration failure during restore
1. Capture the failing migration id from `docker compose logs backend`.
2. Roll back to the last verified backup.
3. Annotate the failing migration as `rollback-limited` before the next release.

### Worker startup failure
1. Inspect `docker compose logs worker-critical worker-default worker-background`.
2. Validate Redis and database secrets.
3. Restart only the failed worker after the dependency issue is fixed.

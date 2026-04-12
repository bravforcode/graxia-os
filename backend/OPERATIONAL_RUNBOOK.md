# Operational Runbook

Operational guide for the current Personal OS backend. This runbook is aligned with the code paths mounted by `backend/app/main.py` and the scripts in `backend/scripts/`.

## Core Commands

Start the local stack:

```bash
docker compose up -d
```

View backend logs:

```bash
docker compose logs -f backend
```

Stop the stack:

```bash
docker compose down
```

Run backend tests:

```bash
cd backend
python -m pytest tests -q
```

Export the OpenAPI spec:

```bash
cd backend
python scripts/export_openapi.py --output openapi.json
```

Run smoke tests against a running stack:

```bash
bash backend/scripts/smoke_tests.sh
```

## Monitoring Endpoints

Use these first before digging through logs:

- `GET /health`
- `GET /metrics`
- `GET /api/v1/system/health`
- `GET /api/v1/system/costs`
- `GET /api/v1/system/scraper-health`
- `GET /api/v1/costs/summary`
- `GET /api/v1/events/health`
- `GET /api/v1/events/stats`
- `GET /api/v1/scrapers/health`
- `GET /api/v1/scrapers/stats`

Quick checks:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/system/health
curl http://localhost:8000/api/v1/costs/summary
curl http://localhost:8000/api/v1/scrapers/health
curl http://localhost:8000/api/v1/events/health
curl http://localhost:8000/metrics
```

## Incident Playbooks

### 1. Backend does not boot cleanly

Symptoms:

- `/health` returns non-200
- `/api/v1/system/health` reports `blocked` or `degraded`
- backend container exits or restarts repeatedly

Actions:

```bash
docker compose logs --tail=200 backend
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/system/health
```

If the issue is configuration-related:

- verify `.env` exists at the repo root
- compare required settings with `.env.example`
- check database and redis connectivity from Docker Compose

### 2. Database backup

Create a compressed SQL backup from the running local postgres container:

```bash
bash backend/scripts/backup_database.sh
```

Optional:

- set `BACKUP_DIR` to override the backup destination
- set `AWS_S3_BUCKET` to upload the resulting archive if the `aws` CLI is installed

Expected output:

- local file under `backups/backup_YYYYMMDD_HHMMSS.sql.gz`

### 3. Database restore

Restore from a compressed backup:

```bash
bash backend/scripts/restore_database.sh backups/backup_YYYYMMDD_HHMMSS.sql.gz
```

Non-interactive restore:

```bash
bash backend/scripts/restore_database.sh --yes backups/backup_YYYYMMDD_HHMMSS.sql.gz
```

Post-restore verification:

```bash
bash backend/scripts/smoke_tests.sh
cd backend && python -m pytest tests -q
```

### 4. Scraper degradation

Symptoms:

- `/api/v1/scrapers/health` shows muted or failing sources
- `/api/v1/system/scraper-health` shows rising `consecutive_failures`
- job discovery volume drops unexpectedly

Actions:

```bash
curl http://localhost:8000/api/v1/scrapers/health
curl http://localhost:8000/api/v1/system/scraper-health
docker compose logs --tail=200 backend
```

Focus areas:

- upstream website changes
- OpenClaw key or quota issues
- scheduler drift
- database write failures during scraper runs

### 5. Google Workspace integration degraded

Symptoms:

- inbox or calendar summaries fail
- personal assistant or email manager outputs are empty

Actions:

```bash
curl http://localhost:8000/api/v1/integrations/google/health
curl http://localhost:8000/api/v1/integrations/google/gmail/inbox-summary
curl http://localhost:8000/api/v1/integrations/google/calendar/today
docker compose logs --tail=200 backend
```

Focus areas:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REFRESH_TOKEN`
- `GOOGLE_WORKSPACE_EMAIL`

## Deployment Checklist

Before promoting a build:

1. `cd backend && python -m pytest tests -q`
2. `cd backend && python scripts/export_openapi.py --output openapi.json`
3. `bash -n backend/scripts/backup_database.sh`
4. `bash -n backend/scripts/restore_database.sh`
5. `bash -n backend/scripts/smoke_tests.sh`
6. `docker compose -f docker-compose.yml config > /dev/null`
7. `bash backend/scripts/smoke_tests.sh` against the running target stack

## Rollback

If a deployment is unhealthy:

1. collect logs from `backend`, `postgres`, and `redis`
2. restore the last known good database backup if schema or data was corrupted
3. bring the previous image or compose revision back online
4. rerun smoke tests and `/health` checks before reopening traffic

Minimum rollback verification:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/system/health
bash backend/scripts/smoke_tests.sh
```

## CI Reference

GitHub Actions workflow:

- `.github/workflows/ci.yml`

Current CI validates:

- backend tests
- OpenAPI export
- frontend lint and build
- shell script syntax
- Docker Compose configuration rendering

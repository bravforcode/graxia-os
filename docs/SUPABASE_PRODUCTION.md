# Supabase Production Always-On Runbook

This is the production path for running Personal OS as an always-on Docker stack with Supabase as the primary PostgreSQL database.

## Runtime Shape

- Supabase Postgres is the source of truth for application data.
- Local Docker Redis is the broker/cache for Celery, rate limits, beat locks, and queues.
- Celery workers are split into `critical`, `default`, and `background` queues.
- Celery Beat is the single scheduler for autonomous jobs.
- Caddy terminates TLS and routes frontend, API, health, n8n, and webhooks.
- n8n starts with bundled workflow import before launching.
- Monitoring includes Prometheus, Alertmanager, Grafana, Loki, Promtail, cAdvisor, node exporter, Redis exporter, and Flower on the internal network.

## Supabase Connection Choice

Use these connection strings from the Supabase Dashboard `Connect` panel:

- `DATABASE_URL`: Supavisor session pooler on port `5432` for persistent backend and worker traffic when IPv4 is required.
- `DATABASE_MIGRATION_URL`: direct database connection on port `5432` for migrations, `pg_dump`, and backups when the host supports IPv6. If IPv6 is unavailable, use session pooler here too.
- Transaction pooler on port `6543` is supported by this app with `NullPool` and disabled asyncpg statement cache, but it is not the preferred always-on worker path.

Include `?sslmode=require` on Supabase URLs.

## First-Time Setup

```bash
cp .env.production.template .env.production
```

Fill every placeholder in `.env.production`. Production startup is intentionally strict and will refuse unsafe placeholders.

Minimum required groups:

- Real public URLs: `APP_HOST`, `APP_BASE_URL`, `FRONTEND_URL`, `ALLOWED_CORS_ORIGINS`
- Secrets: `SECRET_KEY`, `ENCRYPTION_KEY`, `JWT_SIGNING_KEYS`, `CSRF_SECRET`
- TLS and routing: `CADDY_EMAIL`
- Supabase: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`, `DATABASE_MIGRATION_URL`, `POSTGRES_PASSWORD`
- Redis: `REDIS_PASSWORD`, `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
- Control plane: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `ALERTMANAGER_WEBHOOK_TOKEN`
- Operations passwords: `FLOWER_BASIC_AUTH`, `N8N_PASSWORD`, `GRAFANA_ADMIN_PASSWORD`
- AI: at least one real `OPENCLAW_API_KEY` or `GEMINI_API_KEY`
- Backups: `BACKUP_BUCKET`, `BACKUP_REGION`, `BACKUP_ENCRYPTION_PUBLIC_KEY`, `BACKUP_ENCRYPTION_PRIVATE_KEY_FILE`

`frontend/.env.production` may keep placeholder `VITE_*` values in git. Production Docker builds now inject the real frontend runtime values from `.env.production` through compose build args. The frontend must receive:

- `VITE_API_BASE_URL`
- `VITE_AGENT_STREAM_URL`
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`

Do not put `SUPABASE_SERVICE_ROLE_KEY` in any frontend build or client env.

Create required local directories and secret files:

```bash
mkdir -p logs/caddy logs/backend data/obsidian secrets
printf '%s\n' 'PASTE_AGE_PRIVATE_KEY_HERE' > secrets/backup_private_key.txt
printf '%s\n' "$ALERTMANAGER_WEBHOOK_TOKEN" > secrets/alertmanager_webhook_token.txt
chmod 600 secrets/backup_private_key.txt secrets/alertmanager_webhook_token.txt
```

## Preflight, Migrate, Start

```bash
make supabase-env-audit
docker compose --env-file .env.production -f docker-compose.supabase.yml config --quiet
docker compose --env-file .env.production -f docker-compose.supabase.yml build
docker compose --env-file .env.production -f docker-compose.supabase.yml run --rm backend python scripts/production_preflight.py
docker compose --env-file .env.production -f docker-compose.supabase.yml run --rm backend python scripts/alembic_safe.py upgrade head
docker compose --env-file .env.production -f docker-compose.supabase.yml up -d
```

Equivalent Make targets:

```bash
make supabase-env-audit
make supabase-preflight
make supabase-prod-migrate
make supabase-prod-up
```

`make supabase-env-audit` is the fast fail gate. It validates strict production settings before Docker preflight and checks that the frontend compose build still bridges the required `VITE_*` args from `.env.production`.

## Install Always-On Service

On a Linux host where the repo lives at `/opt/personal-os`:

```bash
sudo cp deploy/systemd/personal-os-supabase.service /etc/systemd/system/personal-os.service
sudo systemctl daemon-reload
sudo systemctl enable --now personal-os.service
sudo systemctl status personal-os.service
```

## Verify

```bash
curl -fsS https://$APP_HOST/health
curl -fsS https://$APP_HOST/api/v1/system/health
docker compose --env-file .env.production -f docker-compose.supabase.yml ps
docker compose --env-file .env.production -f docker-compose.supabase.yml logs --tail=200 backend beat worker-critical
```

Run a public smoke test:

```bash
python deploy/scripts/smoke_test.py --target "https://$APP_HOST"
```

## Autonomous Jobs Owned by Beat

The production stack sets `SCHEDULER_EMBEDDED=false`; scheduled automation is owned by the `beat` service only. Current beat schedule includes:

- Daily database backup
- Weekly restore drill
- DLQ depth check every 15 minutes
- Daily scan
- Morning briefing
- Follow-up check
- Job discovery twice daily
- Email processing every 30 minutes
- Weekly review and weekly strategy
- Monthly identity snapshot
- Obsidian daily note and refresh
- Redis backup

## Operational Rule

Do not run both embedded backend scheduler and Celery Beat in production. That creates duplicate autonomous actions. Keep `SCHEDULER_EMBEDDED=false` in `.env.production`.

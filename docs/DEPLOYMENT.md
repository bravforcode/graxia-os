# Deployment Notes

This repository currently has a verified development baseline. Treat production deployment as an environment-specific exercise until real infrastructure, secret rotation, backup, and monitoring policies are defined.

## Supabase Production

Use `docker-compose.supabase.yml` for the always-on production stack when Supabase is the PostgreSQL source of truth.

```bash
cp .env.production.template .env.production
make supabase-preflight
make supabase-prod-migrate
make supabase-prod-up
```

Install the systemd unit for autonomous restarts:

```bash
sudo cp deploy/systemd/personal-os-supabase.service /etc/systemd/system/personal-os.service
sudo systemctl daemon-reload
sudo systemctl enable --now personal-os.service
```

See `docs/SUPABASE_PRODUCTION.md` for the full runbook.

## Compose Preview

```bash
make up
make migrate
```

Check:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/system/health
```

## Required Runtime Decisions

- Use Supabase PostgreSQL for production runtime data, preferably Direct or Supavisor Session mode for long-running backend and worker services.
- Use Redis for rate limiting and event-related runtime support.
- Provide strong `SECRET_KEY` and `ENCRYPTION_KEY` values through the deployment secret store.
- Set `ALLOWED_CORS_ORIGINS` to explicit frontend origins; do not use wildcard origins with credentials.
- Run `python scripts/alembic_safe.py upgrade head` before serving traffic.

## Frontend Routing

The React app in `frontend/` is the canonical UI. The old static `dashboard/` directory is legacy and is not mounted by the FastAPI backend.

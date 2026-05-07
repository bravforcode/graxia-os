# Secrets Rotation Runbook
**Project:** Graxia Revenue OS
**Last updated:** 2026-04-30

---

## Overview

This runbook covers rotating every secret in production. Run it any time a secret is
suspected compromised, on a scheduled 90-day cadence, or when a team member leaves.

Each section follows: **Generate → Deploy → Verify → Revoke old**.

---

## Secret Inventory

| Secret | Where set | Rotation frequency | Owner |
|---|---|---|---|
| `SECRET_KEY` (JWT signing) | Doppler / `.env` | 90 days | Backend |
| `DATABASE_URL` password | Supabase + Doppler | On breach | Backend |
| `REDIS_PASSWORD` | Redis Cloud + Doppler | 90 days | Backend |
| `OPENCLAW_API_KEY` | OpenClaw dashboard + Doppler | On breach | Backend |
| `GEMINI_API_KEY` | Google Cloud + Doppler | On breach | Backend |
| `TELEGRAM_BOT_TOKEN` | BotFather + Doppler | On breach | Backend |
| `ALERTMANAGER_WEBHOOK_SECRET` | Doppler + Alertmanager config | 90 days | DevOps |
| `ALERTMANAGER_WEBHOOK_TOKEN` | Doppler + Alertmanager config | 90 days | DevOps |
| `INTERNAL_METRICS_TOKEN` | Doppler | 90 days | DevOps |
| `STRIPE_WEBHOOK_SECRET` | Stripe dashboard + Doppler | On Stripe rotation | Finance |
| `ADMIN_DEFAULT_PASSWORD` | Doppler | 90 days | Admin |
| `ENCRYPTION_KEY` | Doppler | 180 days | Backend |
| `JWT_SIGNING_KEYS` (multi-kid) | Doppler | 90 days | Backend |

---

## Rotation Procedures

### SECRET_KEY / JWT_SIGNING_KEYS

JWT rotation uses kid-based key versioning. Old tokens stay valid during the grace period.

```bash
# 1. Generate new signing key
NEW_KEY=$(openssl rand -hex 32)

# 2. Add new kid to JWT_SIGNING_KEYS in Doppler
#    Format: {"v2": "<new_key>", "v1": "<old_key>"}
#    Doppler: doppler secrets set JWT_SIGNING_KEYS='{"v2":"<new>","v1":"<old>"}'
#    Doppler: doppler secrets set JWT_ACTIVE_KID=v2

# 3. Deploy: all new tokens use v2, old v1 tokens still validate
#    Wait for max ACCESS_TOKEN_EXPIRE_MINUTES (15 min) before removing v1

# 4. After grace period, remove old kid:
#    doppler secrets set JWT_SIGNING_KEYS='{"v2":"<new>"}'
```

**Verification:** `curl https://api.graxia.app/api/v1/auth/me -H "Authorization: Bearer <new_token>"` → 200

---

### DATABASE_URL Password

```bash
# 1. In Supabase dashboard → Settings → Database → Reset password
#    Copy new password

# 2. Update Doppler
doppler secrets set DATABASE_URL="postgresql+asyncpg://postgres:<NEW_PASSWORD>@<host>:5432/postgres"

# 3. Deploy backend (new containers pick up new URL)

# 4. Verify health endpoint returns 200
curl https://api.graxia.app/health
```

**Warning:** Old connections (if using a connection pooler) may hold old credentials for up to
`DB_POOL_RECYCLE_SECONDS` (default 1800s). Trigger a rolling restart to flush the pool.

---

### REDIS_PASSWORD

```bash
# 1. In Redis Cloud → Databases → Security → Regenerate password
NEW_REDIS_PASS=$(openssl rand -base64 32)

# 2. Update Doppler
doppler secrets set REDIS_PASSWORD="<new_password>"
doppler secrets set CELERY_BROKER_URL="redis://:<new_password>@<host>:6379/1"
doppler secrets set CELERY_RESULT_BACKEND="redis://:<new_password>@<host>:6379/2"

# 3. Deploy
# 4. Verify Celery workers reconnect
docker exec graxia_celery celery -A app.tasks inspect ping
```

---

### TELEGRAM_BOT_TOKEN

```bash
# 1. In Telegram: message @BotFather → /mybots → select bot → API Token → Revoke
#    BotFather provides new token immediately

# 2. Update Doppler
doppler secrets set TELEGRAM_BOT_TOKEN="<new_token>"

# 3. If using webhook mode, re-register:
curl -X POST "https://api.telegram.org/bot<NEW_TOKEN>/setWebhook" \
  -d "url=https://api.graxia.app/api/v1/integrations/alerts/telegram" \
  -d "secret_token=<ALERTMANAGER_WEBHOOK_SECRET>"

# 4. Verify bot responds to /start
```

---

### ALERTMANAGER_WEBHOOK_SECRET

```bash
# 1. Generate
NEW_SECRET=$(openssl rand -hex 32)

# 2. Update Doppler
doppler secrets set ALERTMANAGER_WEBHOOK_SECRET="$NEW_SECRET"

# 3. Update Alertmanager config (alertmanager.yml):
#    webhook_configs:
#      - url: 'https://api.graxia.app/api/v1/integrations/alerts/telegram'
#        http_config:
#          headers:
#            X-Alertmanager-Signature: 'sha256=<compute_hmac_of_body>'
#    Alertmanager does NOT natively support HMAC signing — use a proxy script or
#    update to use X-Alertmanager-Token (bearer token) if simpler.

# 4. Reload Alertmanager config
curl -X POST http://localhost:9093/-/reload

# 5. Verify a test alert reaches Telegram
```

---

### INTERNAL_METRICS_TOKEN

```bash
NEW_TOKEN=$(openssl rand -hex 32)
doppler secrets set INTERNAL_METRICS_TOKEN="$NEW_TOKEN"

# Verify /metrics is accessible:
curl -H "X-Internal-Token: $NEW_TOKEN" https://api.graxia.app/metrics | head -5
```

---

### STRIPE_WEBHOOK_SECRET

```bash
# Stripe rotates the signing secret when you roll the endpoint.
# 1. Stripe Dashboard → Developers → Webhooks → select endpoint → Roll signing secret
# 2. Copy new whsec_... value
# 3. doppler secrets set STRIPE_WEBHOOK_SECRET="whsec_<new>"
# 4. Deploy
# 5. Trigger a test event from Stripe dashboard to verify delivery
```

---

## Emergency Revocation Checklist

Use when a secret is confirmed compromised:

- [ ] Immediately revoke the secret at the source (Supabase, Redis Cloud, BotFather, etc.)
- [ ] Rotate `SECRET_KEY` / JWT keys — all existing sessions are invalidated
- [ ] Rotate `DATABASE_URL` — stops DB access with old credentials
- [ ] Update Doppler and trigger zero-downtime deploy
- [ ] Review audit log for unauthorized access: `GET /api/v1/admin/audit-log?action=auth.login&limit=100`
- [ ] Check `openclaw_usage` and `api_rate_limits` tables for unusual activity
- [ ] Post incident report within 24 hours

---

## Automated Rotation with Doppler

Doppler can trigger a redeploy on secret change. Configure the Doppler webhook to call
your Railway/Render/Fly.io deployment hook:

```bash
# Doppler project settings → Webhooks → Add webhook
# Trigger: "Secret Changed"
# URL: https://api.railway.app/v1/services/<SERVICE_ID>/deployments
# Headers: Authorization: Bearer <RAILWAY_TOKEN>
```

This ensures any rotation in Doppler immediately triggers a rolling deploy with fresh secrets.

---

## Rotation Schedule (Calendar)

| Date | Action |
|---|---|
| 2026-07-30 | Rotate SECRET_KEY, JWT_SIGNING_KEYS, REDIS_PASSWORD, INTERNAL_METRICS_TOKEN |
| 2026-10-30 | Full rotation cycle |
| 2027-01-30 | Full rotation cycle + ENCRYPTION_KEY |

Add to team calendar with a 1-week reminder.

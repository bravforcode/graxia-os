# Credential Rotation Checklist

**Complete EVERY item before deploying to production.**
**Do this rotation BEFORE any commit that pushes to a public or shared remote.**

---

## ⚠️ Why rotation is needed

`.env.production` on disk contains all production secrets as plain text.
If this file has been accessed by any process other than intended, all credentials below must be treated as compromised.

---

## Rotation order (do in this sequence — some depend on others)

### 1. OPENCLAW_API_KEY (`sk-or-v1-…`)
- [ ] Log in to your OpenClaw / OpenRouter dashboard
- [ ] Generate a new API key
- [ ] Update in your secrets manager (Doppler/AWS) and `.env.production`
- [ ] Revoke the old key
- [ ] Verify: `curl -H "Authorization: Bearer <NEW_KEY>" https://api.openclaw.ai/v1/models`

### 2. GEMINI_API_KEY (`AIzaSy…`)
- [ ] Go to [console.cloud.google.com](https://console.cloud.google.com) → APIs & Services → Credentials
- [ ] Create a new API key with the same restrictions
- [ ] Update in secrets manager and `.env.production`
- [ ] Delete the old key
- [ ] Verify the Gemini fallback works in dev mode

### 3. GOOGLE_CLIENT_SECRET + GOOGLE_REFRESH_TOKEN
- [ ] Go to Google Cloud Console → OAuth 2.0 clients → your client → regenerate secret
- [ ] Update `GOOGLE_CLIENT_SECRET` in secrets manager
- [ ] Re-run the OAuth consent flow to get a new `GOOGLE_REFRESH_TOKEN`:
  ```bash
  python scripts/get_google_token.py
  ```
- [ ] Update `GOOGLE_REFRESH_TOKEN` in secrets manager
- [ ] Verify Google Workspace integration works (calendar, email)

### 4. TELEGRAM_BOT_TOKEN (`8757840873:…`)
- [ ] Message @BotFather on Telegram → `/mybots` → select bot → `API Token` → `Revoke current token`
- [ ] Copy the new token
- [ ] Update `TELEGRAM_BOT_TOKEN` in secrets manager and `.env.production`
- [ ] Restart backend and verify Telegram bot responds to `/start`

### 5. SUPABASE_SERVICE_ROLE_KEY
- [ ] Go to [app.supabase.com](https://app.supabase.com) → your project → Settings → API
- [ ] Click "Generate new service role key"
- [ ] Update `SUPABASE_SERVICE_ROLE_KEY` in secrets manager and `.env.production`
- [ ] Update `DATABASE_URL` if the password changed
- [ ] Verify backend can still connect: `GET /api/v1/system/health`

### 6. DATABASE_URL password (`apF1Z85ZGdbgPRdW`)
- [ ] Go to Supabase Dashboard → Settings → Database → Reset database password
- [ ] Generate a new strong password: `openssl rand -hex 24`
- [ ] Update `DATABASE_URL`, `DATABASE_MIGRATION_URL`, and `POSTGRES_PASSWORD` atomically
- [ ] Restart all services simultaneously (backend + celery + beat)
- [ ] Verify: `GET /health` returns 200

### 7. REDIS_PASSWORD (`3Ch4XEjmKp9V…`)
- [ ] Generate new: `openssl rand -hex 32`
- [ ] Update `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, and docker-compose `REDIS_PASSWORD`
- [ ] Restart Redis container + backend + celery + beat simultaneously
- [ ] Verify Celery tasks are executing: check `/api/v1/system/health` for worker status

### 8. GRAFANA_ADMIN_PASSWORD
- [ ] Generate new: `openssl rand -base64 24`
- [ ] Update in docker-compose and secrets manager
- [ ] Log in to Grafana at http://localhost:3000 with new password to verify

### 9. SERPAPI_KEY (`fdd041d57af8…`)
- [ ] Log in to [serpapi.com](https://serpapi.com) → Account → API Key → Regenerate
- [ ] Update in secrets manager and `.env.production`

### 10. ADMIN_DEFAULT_PASSWORD
- [ ] Generate new: `openssl rand -base64 24`
- [ ] Update in secrets manager
- [ ] On next deployment, the seed will use the new password
- [ ] Log in to the app with the new credentials and verify admin access

### 11. ALERTMANAGER_WEBHOOK_TOKEN
- [ ] Generate new: `openssl rand -hex 32`
- [ ] Update in secrets manager and Alertmanager configuration
- [ ] Update in `secrets/alertmanager_webhook_token.txt`

### 12. N8N_PASSWORD
- [ ] Generate new: `openssl rand -base64 24`
- [ ] Update in docker-compose and secrets manager
- [ ] Log in to n8n at http://localhost:5678 with new password

---

## After ALL rotations are complete

- [ ] Shred the plain-text production env file:
  ```bash
  # On Linux/Mac:
  shred -u .env.production
  # On Windows:
  cipher /w:.env.production
  del .env.production
  ```
- [ ] Set up Doppler (or equivalent) so secrets are never stored as flat files:
  See `docs/SECRETS_MANAGEMENT.md`
- [ ] Verify `.env.production` is in `.gitignore`:
  ```bash
  grep ".env.production" .gitignore
  ```
- [ ] Consider removing `frontend/.env.production` from git tracking:
  ```bash
  git rm --cached frontend/.env.production
  echo "frontend/.env.production" >> .gitignore
  git commit -m "security: stop tracking frontend env file"
  ```
  Then inject `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` via Vercel Environment Variables instead.
- [ ] Run a final secret scan:
  ```bash
  grep -rIn --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=dist \
    -E "(sk-or-v1-|AIzaSy|GOCSPX-|apF1Z85ZGdbgPRdW|3Ch4XEjm)" . \
    | grep -v ".env.example\|CREDENTIAL_ROTATION_CHECKLIST"
  ```
  Expected: zero matches.

---

## Rotation log

| Credential | Rotated on | Rotated by |
|---|---|---|
| OPENCLAW_API_KEY | | |
| GEMINI_API_KEY | | |
| GOOGLE_CLIENT_SECRET | | |
| GOOGLE_REFRESH_TOKEN | | |
| TELEGRAM_BOT_TOKEN | | |
| SUPABASE_SERVICE_ROLE_KEY | | |
| DATABASE_URL password | | |
| REDIS_PASSWORD | | |
| GRAFANA_ADMIN_PASSWORD | | |
| SERPAPI_KEY | | |
| ADMIN_DEFAULT_PASSWORD | | |
| ALERTMANAGER_WEBHOOK_TOKEN | | |
| N8N_PASSWORD | | |

# Secrets Rotation Procedure — Quant OS

> **DOCUMENTATION ONLY.** This runbook does NOT perform any rotation.

## Pre-Rotation Checklist

- [ ] Change request approved and recorded against current phase
- [ ] Backup of current `.env` saved to encrypted archive
- [ ] Audit log entry started
- [ ] Off-peak window scheduled (low/no live trading)
- [ ] Rollback path tested in staging
- [ ] Notifications sent

## Rotation Order (most → least critical)

1. **MT5_PASSWORD** — broker access; trading halts if wrong
2. **ADMIN_API_KEY** — controls kill switch and mode change
3. **TELEGRAM_BOT_TOKEN** — controls kill switch via Telegram
4. **WEBHOOK_HMAC_SECRET** / **TV_WEBHOOK_SECRET** — controls signal ingestion
5. **DATABASE_URL** / **DB_PASSWORD** — data plane
6. **JWT_SECRET_KEY** — auth token signing
7. **API_KEY** — orders/positions auth
8. **FRED_API_KEY** — non-critical (macro data only)
9. **SENTRY_DSN** — observability, low blast radius
10. LLM API keys — non-critical
11. **TELEGRAM_WEBHOOK_SECRET** — secondary auth on Telegram webhook

## Procedure per Secret

### Step 1: Generate
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Step 2: Stage
- Add to vault
- Update `.env` on staging host
- Verify staging health check passes

### Step 3: Apply
```bash
cp .env .env.$(date +%Y%m%d-%H%M).bak
# Edit .env, replace the single value
# Restart service
systemctl restart quant-os
# or: docker compose restart
```

### Step 4: Verify
```bash
curl -fsS http://localhost:8000/health
```

### Step 5: Revoke
- Revoke old secret at provider
- Confirm no auth attempts succeed with old value

### Step 6: Record
- Update rotation log
- Commit change-request closure

## Tooling

- **Scanning:** `python scripts/secret_scan.py`
- **Health:** `curl http://localhost:8000/health`
- **Secret gen:** `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`

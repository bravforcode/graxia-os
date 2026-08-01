# Secret Rotation Checklist — Quant OS

> **DOCUMENTATION ONLY — DO NOT ROTATE UNTIL APPROVED.**

## Secret Inventory

| # | Secret | Env var | Used in | Storage |
|---|---|---|---|---|
| 1 | MT5 broker password | `MT5_PASSWORD` | `core/config.py:166`, `execution/adapters/manager.py:51` | `.env` |
| 2 | MT5 login | `MT5_LOGIN` | `core/config.py:165` | `.env` |
| 3 | Telegram bot token | `TELEGRAM_BOT_TOKEN` | `api/telegram_server.py:50`, `api/telegram_commands.py:104`, `monitoring/alerts.py:59` | `.env` |
| 4 | Telegram chat ID | `TELEGRAM_CHAT_ID` | `api/telegram_server.py:55`, `api/telegram_commands.py:105` | `.env` |
| 5 | Telegram webhook secret | `TELEGRAM_WEBHOOK_SECRET` | `api/telegram_server.py:60` | `.env` |
| 6 | TradingView webhook secret | `TV_WEBHOOK_SECRET` | `api/webhook_receiver.py:122-128` | `.env` |
| 7 | Webhook HMAC secret | `WEBHOOK_HMAC_SECRET` | `api/webhook.py:153`, `core/config.py:173` | `.env` |
| 8 | Admin API key | `ADMIN_API_KEY` | `core/config.py:174`, `api/admin.py:34` | `.env` |
| 9 | API key (general) | `API_KEY` | `core/config.py:175`, `api/auth.py:31-41` | `.env` |
| 10 | JWT secret | `JWT_SECRET_KEY` | `core/config.py:172` | `.env` |
| 11 | FRED API key | `FRED_API_KEY` | `core/data/fred_client.py:35` | `.env` |
| 12 | PostgreSQL DSN | `DATABASE_URL` | `core/config.py:161` | `.env` |
| 13 | Redis URL | `REDIS_URL` | `core/config.py:162` | `.env` |
| 14 | Anthropic API key | `ANTHROPIC_API_KEY` | `gold_bot/ai/validator.py:28` | `.env` |
| 15 | Sentry DSN | `SENTRY_DSN` | `core/config.py:142` | `.env` |

## Per-Secret Rotation Steps

For each row:
1. Generate replacement secret
2. Set new value in vault (1Password / AWS Secrets Manager)
3. Update `.env` on the running host (NOT committed)
4. Restart affected service / reload config
5. Verify auth works
6. Revoke old secret at provider
7. Record event in audit log

## Verification

```bash
# Confirm new value loaded
python -c "from graxia.packages.quant_os.core.config import get_config; c=get_config(); print('OK')"
# Health check
curl -fsS http://localhost:8000/health
```

## Rollback Plan

1. Restore previous `.env` from encrypted backup
2. Restart service
3. Verify health endpoint
4. Re-enable old secret at provider if needed
5. File postmortem if rotation was emergency

## Emergency Rotation (Suspected Compromise)

1. Trigger kill switch IMMEDIATELY (Telegram `/kill` or admin API)
2. Stop all new orders
3. Revoke secret at provider FIRST
4. Generate new secret and apply
5. Investigate: check `logs/` for unauthorized use
6. File incident report within 4h
7. Rotate ALL related secrets in the same incident

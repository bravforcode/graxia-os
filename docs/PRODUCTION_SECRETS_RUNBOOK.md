# Production Secrets Runbook

> Comprehensive guide for managing all production secrets.
> **Never commit secrets to version control. Never print secrets in logs or error messages.**

## Secret Inventory

| Secret | Source | Where Used | Rotation |
|--------|--------|------------|----------|
| `SECRET_KEY` | Generated locally | JWT signing, CSRF signing | 90 days |
| `ENCRYPTION_KEY` | Generated locally | Data encryption | 180 days |
| `POSTGRES_PASSWORD` | Generated locally | Database access | 90 days |
| `SUPABASE_URL` | Supabase dashboard | Database connection | On change |
| `SUPABASE_ANON_KEY` | Supabase dashboard | Auth anon access | On change |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase dashboard | Admin API access | On change |
| `STRIPE_SECRET_KEY` | Stripe dashboard | Payment processing | On rotation |
| `STRIPE_WEBHOOK_SECRET` | Stripe dashboard | Webhook verification | On rotation |
| `RESEND_API_KEY` | Resend dashboard | Email delivery | On rotation |
| `OPENCLAW_API_KEY` | OpenClaw dashboard | LLM API access | On rotation |
| `GEMINI_API_KEY` | Google Cloud Console | LLM fallback | On rotation |
| `TELEGRAM_BOT_TOKEN` | BotFather | Alert notifications | On rotation |
| `GOOGLE_CLIENT_ID` | Google Cloud Console | OAuth | On rotation |
| `GOOGLE_CLIENT_SECRET` | Google Cloud Console | OAuth | On rotation |
| `GOOGLE_REFRESH_TOKEN` | OAuth flow | Google API access | On rotation |
| `SENTRY_DSN` | Sentry dashboard | Error tracking | On rotation |

## Where Secrets Live

- **Development:** `.env` file (local, never committed)
- **Staging:** `.env.staging` file or CI/CD secrets store
- **Production:** Doppler secrets manager (preferred) or `.env.production` (file-based)

## Secret Requirements

| Secret | Min Length | Min Entropy | Validation |
|--------|-----------|-------------|------------|
| `SECRET_KEY` | 64 chars (production) / 32 chars (dev) | 4.0 | `_looks_placeholder`, weak secret detection |
| `ENCRYPTION_KEY` | 32 chars | 3.0 | `_looks_placeholder`, weak secret detection |
| `POSTGRES_PASSWORD` | 16 chars | 2.5 | `_looks_placeholder`, weak secret detection |

## Placeholder Detection

The system rejects secrets that match any of these patterns:

- `changeme`, `change-me`
- `your_*`, `your-*` (e.g., `your_secret_key_here`)
- `paste_*` (e.g., `paste_your_key_here`)
- `placeholder`, `example`, `development-secret`
- `replace`, `example.com`, `your-domain.com`

## Setting Up Secrets for Production

1. Generate secrets:
   ```bash
   SECRET_KEY=$(openssl rand -hex 32)        # 64 chars
   ENCRYPTION_KEY=$(openssl rand -hex 32)     # 64 chars
   POSTGRES_PASSWORD=$(openssl rand -base64 24)  # 32 chars
   ```

2. Add to `.env.production`:
   ```bash
   echo "SECRET_KEY=$SECRET_KEY" >> .env.production
   echo "ENCRYPTION_KEY=$ENCRYPTION_KEY" >> .env.production
   echo "POSTGRES_PASSWORD=$POSTGRES_PASSWORD" >> .env.production
   ```

3. Verify no placeholders remain:
   ```bash
   grep -n "changeme\|placeholder\|your_\|paste_\|replace\|example" .env.production
   # Expected: no output
   ```

4. Verify application boots:
   ```bash
   cd backend && python -c "from app.config import settings; print('OK')"
   ```

## Emergency: Secret Compromised

1. Immediately rotate the compromised secret at its source
2. Update the corresponding env variable
3. Restart all services
4. Check audit logs for unauthorized access
5. Post incident report within 24 hours

See `docs/SECRETS_ROTATION_RUNBOOK.md` for detailed rotation procedures.

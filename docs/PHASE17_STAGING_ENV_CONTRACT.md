# Phase 17 — Staging Environment Contract

> Defines required environment variables for staging runtime.
> Names only — no values. Placeholders where needed.

## Required Variables

### Mode

```
APP_ENV=staging
```

### Security Gates

```
ALLOW_LIVE_STRIPE=false
ALLOW_REAL_EMAIL_SEND=false
ALLOW_REAL_GOOGLE_MUTATION=false
ALLOW_REAL_LLM_CALLS=false
```

### Rate Limiting

```
RATE_LIMIT_BACKEND=inmemory|redis
```

### Database (placeholder only — never live Supabase)

```
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/graxia_staging
```

### Redis (placeholder only)

```
REDIS_URL=redis://localhost:6379/0
```

### Auth Secrets (generated per environment)

```
SECRET_KEY=<generated: openssl rand -hex 32>
ENCRYPTION_KEY=<generated: openssl rand -hex 32>
```

### CORS

```
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173,https://staging.graxia.com
```

## Variable Categories

| Category | Enforcement | Notes |
|----------|-------------|-------|
| **APP_ENV** | Must be `staging` | Triggers staging readiness path |
| **Live provider gates** | All must be `false` | Verified by readiness endpoint |
| **Rate limit** | `inmemory` for single-instance, `redis` for multi | Staging defaults to `inmemory` |
| **Database** | Local only (no Supabase) | Migration URL must match |
| **Secrets** | Generated, not checked in | Reject placeholders at boot |

## Enforced Defaults (tested in test_production_auth_gate.py)

| Setting | Default | Staging Expectation |
|---------|---------|-------------------|
| `ALLOW_LIVE_STRIPE` | false | false |
| `ALLOW_REAL_EMAIL_SEND` | false | false |
| `ALLOW_REAL_GOOGLE_MUTATION` | false | false |
| `ALLOW_REAL_LLM_CALLS` | false | false |

## What Is NOT Allowed in Staging

- Live Supabase / production database URL
- Live Stripe secret key (sk_live_*)
- Live Resend API key (real sending domain)
- Real Google Workspace write scopes
- Real LLM model calls (gpt-4, claude-3-opus, etc.)
- Production secrets or certificates

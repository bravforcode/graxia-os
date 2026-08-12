# Phase 18 — Production Readiness Contract

> Defines required environment variables, enforced defaults, and go/no-go gates for production dry-run.
> Names only — no values. Placeholders where needed.

## Required Variables

### Mode

```
APP_ENV=production       # Triggers strict production checks
```

### Security Gates (all must be false)

```
ALLOW_LIVE_STRIPE=false
ALLOW_REAL_EMAIL_SEND=false
ALLOW_REAL_GOOGLE_MUTATION=false
ALLOW_REAL_LLM_CALLS=false
ALLOW_PRODUCTION_DB=false
```

### Production Readiness Gate

```
PRODUCTION_READY=false   # Always false until explicit go/no-go
GO_NO_GO_REQUIRED=true
```

### Auth Secrets

```
SECRET_KEY=<generated: openssl rand -hex 32, min 64 chars in production>
ENCRYPTION_KEY=<generated: openssl rand -hex 32, min 32 chars>
POSTGRES_PASSWORD=<generated: openssl rand -base64 24, min 16 chars>
```

### Database (staging/local only — never live Supabase in dry-run)

```
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/graxia_prod_dryrun
```

### Redis (staging/local only)

```
REDIS_URL=redis://localhost:6379/0
```

### CORS

```
ALLOWED_ORIGINS=https://app.graxia.com,https://admin.graxia.com
```

## Variable Categories

| Category | Enforcement | Notes |
|----------|-------------|-------|
| **APP_ENV** | Must be `production` for production checks | Triggers `settings.STRICT_BOOTSTRAP` |
| **Live provider gates** | All must be `false` | Verified by readiness endpoint |
| **Production readiness** | `false` by default | Gate kept closed until go/no-go |
| **Database** | Staging/local only (no live Supabase) | Dry-run mode only |
| **Secrets** | Generated, not checked in | Reject placeholders at boot |

## Enforced Defaults (tested in test_production_auth_gate.py)

| Setting | Default | Production Expectation |
|---------|---------|-----------------------|
| `ALLOW_LIVE_STRIPE` | false | false |
| `ALLOW_REAL_EMAIL_SEND` | false | false |
| `ALLOW_REAL_GOOGLE_MUTATION` | false | false |
| `ALLOW_REAL_LLM_CALLS` | false | false |
| `ALLOW_PRODUCTION_DB` | false | false |
| `PRODUCTION_READY` | false | false |
| `GO_NO_GO_REQUIRED` | true | true |

## What Is NOT Allowed in Production Dry-Run

- Live Supabase / production database URL
- Live Stripe secret key (sk_live_*)
- Live Resend API key (real sending domain)
- Real Google Workspace write scopes
- Real LLM model calls (gpt-4, claude-3-opus, etc.)
- Live production secrets or certificates
- Production webhook endpoints
- Real customer data (use anonymized test data)
- External production integrations

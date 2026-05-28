# Production Go/No-Go Checklist

> **This checklist must be completed and signed off before any production deployment.**
> Until this checklist is 100% green, `PRODUCTION_READY` must remain `false`.

## Section 1: Environment & Secrets

| # | Check | Pass? | Notes |
|---|-------|-------|-------|
| 1.1 | `APP_ENV` is set to `production` | ☐ | |
| 1.2 | `SECRET_KEY` is 64+ chars with high entropy | ☐ | Verify with `openssl rand -hex 32` |
| 1.3 | `ENCRYPTION_KEY` is 32+ chars with high entropy | ☐ | |
| 1.4 | `POSTGRES_PASSWORD` is 16+ chars | ☐ | |
| 1.5 | All Supabase credentials (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`) are real production values | ☐ | |
| 1.6 | All Redis passwords are non-placeholder | ☐ | |
| 1.7 | JWT signing keys configured with kid-based key versioning | ☐ | |
| 1.8 | CORS origins list contains only explicit production origins | ☐ | No wildcards |
| 1.9 | All webhook secrets configured (Stripe, Alertmanager) | ☐ | |

## Section 2: Live Providers

| # | Check | Pass? | Notes |
|---|-------|-------|-------|
| 2.1 | Stripe live-mode secret key configured | ☐ | Must start with `sk_live_` |
| 2.2 | Stripe webhook endpoint registered in production | ☐ | `whsec_*` configured |
| 2.3 | Stripe webhook signing secret matches registered endpoint | ☐ | |
| 2.4 | Email sending domain verified with Resend | ☐ | |
| 2.5 | Google Workspace OAuth consent screen published | ☐ | |
| 2.6 | LLM provider API keys configured (OpenClaw / Gemini) | ☐ | |

## Section 3: Infrastructure

| # | Check | Pass? | Notes |
|---|-------|-------|-------|
| 3.1 | Production PostgreSQL database reachable | ☐ | |
| 3.2 | Production Redis reachable | ☐ | |
| 3.3 | SSL/TLS certificate valid (no expiry within 30 days) | ☐ | |
| 3.4 | DNS records point to production IPs | ☐ | |
| 3.5 | Load balancer / reverse proxy configured | ☐ | |
| 3.6 | Rate limiting backend configured (Redis) | ☐ | |

## Section 4: Monitoring & Alerting

| # | Check | Pass? | Notes |
|---|-------|-------|-------|
| 4.1 | Sentry DSN configured and test event sent | ☐ | |
| 4.2 | Telegram bot token configured and test message received | ☐ | |
| 4.3 | Alertmanager webhook secret configured | ☐ | |
| 4.4 | Metrics endpoint accessible (`/metrics`) | ☐ | |
| 4.5 | Health endpoint returns 200 | ☐ | |
| 4.6 | Prometheus/Grafana dashboards set up | ☐ | |

## Section 5: Backup & Recovery

| # | Check | Pass? | Notes |
|---|-------|-------|-------|
| 5.1 | Automated database backup configured | ☐ | |
| 5.2 | Backup encryption public key configured | ☐ | |
| 5.3 | Backup encryption private key file path configured | ☐ | |
| 5.4 | S3 bucket accessible for backup uploads | ☐ | |
| 5.5 | Recovery procedure tested in last 30 days | ☐ | |
| 5.6 | Rollback procedure documented | ☐ | |

## Section 6: Security

| # | Check | Pass? | Notes |
|---|-------|-------|-------|
| 6.1 | All live provider gates enabled (`ALLOW_LIVE_* = true`) | ☐ | Must be explicit |
| 6.2 | Production readiness gate enabled (`PRODUCTION_READY = true`) | ☐ | Final step |
| 6.3 | MFA enabled for admin accounts | ☐ | |
| 6.4 | Audit log retention configured | ☐ | |
| 6.5 | CSRF protection verified working | ☐ | |
| 6.6 | Rate limiting active and tested | ☐ | |
| 6.7 | Safe error contract verified (no stack/SQL/token leaks) | ☐ | |

## Signoff

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Developer | | | |
| DevOps | | | |
| Security | | | |

## Decision

- [ ] **GO** — All checks pass. Production can proceed.
- [ ] **NO-GO** — Blocked by items: _______________

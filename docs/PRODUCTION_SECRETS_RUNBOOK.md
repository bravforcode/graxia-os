# Production Secrets Runbook

## Principles

- never print raw secrets in logs or tickets
- rotate secrets outside application code
- verify secret presence by name, never by value in reports

## Required Secret Classes

- app/session/jwt signing secrets
- database credentials
- Stripe keys
- email provider credentials
- Google Workspace credentials
- observability/error tracking credentials

## Rotation Flow

1. prepare replacement secret in provider vault
2. update deployment secret store
3. restart/apply configuration
4. verify health/readiness endpoints
5. revoke superseded secret

## Rollback

- restore previous secret version in secret store
- redeploy or restart
- verify `/api/v1/health`

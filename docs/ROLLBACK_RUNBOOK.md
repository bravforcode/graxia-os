# Rollback Runbook

## Use When

- readiness gate regresses
- production incident requires immediate reversal
- migration/app release is unsafe

## Rollback Steps

1. identify last known good release/commit
2. disable risky provider flags if relevant
3. restore previous deployment/configuration
4. verify `/api/v1/health`
5. verify `/api/v1/health/readiness/production`

## Do Not

- force-push history
- delete unknown data
- bypass approval for customer/public actions

# Stripe Production Gate

## Default

- `ALLOW_LIVE_STRIPE=false`
- production gate remains closed

## Preconditions

- test-mode webhook flow verified in staging
- approval flows verified for customer-facing actions
- refund/charge handling playbook reviewed

## Enablement Sequence

1. confirm staging parity
2. confirm live key provisioning outside repo
3. explicit human approval
4. set `ALLOW_LIVE_STRIPE=true`
5. verify production dry-run gate again before any live charge

## Rollback

- set `ALLOW_LIVE_STRIPE=false`
- disable any pending live traffic entrypoint

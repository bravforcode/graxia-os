# Production Go/No-Go Checklist

## Default Position

- `production_ready`: `false`
- `go_no_go_required`: `true`
- live providers stay disabled until explicit approval

## Required Checks

- `/api/v1/health/readiness/staging` verified in a real staging environment
- `/api/v1/health/readiness/production` verified and still closed by default
- database migrations at single head
- rollback docs reviewed
- backup/restore drill reviewed
- rate limiting verified
- approval/audit flows verified
- live provider flags reviewed and still `false` unless explicitly approved

## Required Human Decision

- approve production rollout window
- approve provider enablement sequence
- approve rollback owner and incident commander

## Stop Conditions

- any readiness gate blocker remains
- any live provider flag is `true` without explicit sign-off
- any unresolved migration/data-loss risk exists

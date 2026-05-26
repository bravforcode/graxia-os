# Email Production Gate

## Default

- `ALLOW_REAL_EMAIL_SEND=false`

## Preconditions

- mock/sandbox flows verified
- approval required for customer/public outbound actions
- sender identity/domain verified outside repo

## Enablement Sequence

1. confirm sandbox behavior
2. confirm allow-list / policy review
3. explicit human approval
4. set `ALLOW_REAL_EMAIL_SEND=true`
5. verify audit logging for outbound events

## Rollback

- set `ALLOW_REAL_EMAIL_SEND=false`
- pause outbound queue if applicable

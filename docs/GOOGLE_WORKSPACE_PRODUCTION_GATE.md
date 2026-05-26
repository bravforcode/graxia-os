# Google Workspace Production Gate

## Default

- `ALLOW_REAL_GOOGLE_MUTATION=false`
- `GOOGLE_ENABLE_WRITE_SCOPES=false`

## Preconditions

- read-only workspace tools verified first
- write scopes reviewed
- approval path verified for every write action

## Enablement Sequence

1. verify read-only production dry-run
2. explicit human approval for mutation scope
3. enable write scopes and mutation flag together
4. verify audit trail

## Rollback

- set `ALLOW_REAL_GOOGLE_MUTATION=false`
- set `GOOGLE_ENABLE_WRITE_SCOPES=false`

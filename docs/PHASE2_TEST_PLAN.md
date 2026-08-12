# Phase 2 Test Plan

## Backend verification
Run before backend preservation commits:

```powershell
python -m compileall backend/app
pytest backend/tests/test_auth_context.py -q
pytest backend/tests/test_approval_org_scope.py -q
pytest backend/tests/test_health_readiness.py -q
pytest backend/tests/test_audit_query.py -q
pytest backend/tests/test_env_example_safety.py -q
pytest backend/tests/test_funnel_v5.py -q
pytest backend/tests/test_mcp_foundation.py -q
pytest backend/tests/test_mcp_workflow_tools.py -q
```

## Frontend verification
Run before frontend preservation commit:

```powershell
cd frontend
bun run build
cd ..
```

## Alembic verification
Run before migration preservation commit:

```powershell
alembic heads
```

## Missing or not-found checks at Phase 2 start
- `backend/tests/test_org_context_api.py` — not found
- `backend/tests/test_rate_limit.py` — not found
- `backend/tests/test_observability.py` — not found
- `backend/tests/test_staging_smoke.py` — not found
- `backend/app/api/readiness.py` — not found
- `backend/app/core/rate_limit.py` — not found

## Phase 2 policy
- Do not broaden scope to make missing tests exist.
- If verification fails due to current dirty product diff, document exact failure and stop that commit lane.
- Do not import `agent-stack` to make tests pass.

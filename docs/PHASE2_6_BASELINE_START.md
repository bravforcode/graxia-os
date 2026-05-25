# Phase 2.6 Baseline Start

## Scope

- continue from `Phase 2.5 = PARTIAL`
- no `agent-stack` import
- no shared-contract implementation
- baseline finalization only

## Starting Git State

- branch: `staging`
- tracked dirty files: none
- untracked paths:
  - `extraterrestrial-escape/`
  - `sites/`

## Known Soft Blockers

- `tests/test_api_integration.py` import path instability from repo root
- `tests/test_api_integration.py` `TestClient` compatibility issue with:
  - `fastapi=0.110.0`
  - `starlette=0.36.3`
  - `httpx=0.28.1`
- Alembic command ambiguity from repo root

## Known Hard-Stop Checks

- do not read `.env`
- do not call live providers
- do not import/copy `C:\Users\menum\agent-stack`
- do not use `git add .`
- do not delete unknown directories

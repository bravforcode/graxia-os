# Phase 2.6 API Test Compatibility

## Problem

`tests/test_api_integration.py` failed in two stages:

1. repo-root run:
   - `ModuleNotFoundError: No module named 'app'`
2. retry with backend path:
   - `TypeError: Client.__init__() got an unexpected keyword argument 'app'`

## Root Cause

### Import-path issue

- root test file imports `from app.main import app`
- repo-root pytest had no stable `pythonpath = backend`

### Client compatibility issue

- current stack:
  - `fastapi=0.110.0`
  - `starlette=0.36.3`
  - `httpx=0.28.1`
- legacy `fastapi.testclient.TestClient` path relies on Starlette/httpx behavior no longer compatible with this combo

### Test-noise issue

- importing `app.main` initialized Sentry
- test teardown produced retry/logging noise against `sentry.example.com`
- `backend/app/core/setup.py` already supports `TESTING=true` to skip Sentry init

## Fix Applied

- added root `pytest.ini` with `pythonpath = backend`
- rewrote `tests/test_api_integration.py` to use `httpx.ASGITransport` + `httpx.AsyncClient`
- set `os.environ.setdefault("TESTING", "true")` before importing `app.main`

## Verification

- `pytest tests/test_api_integration.py -q`
- result: `3 passed, 1 skipped`
- skip reason: `TESTSPRITE_API_KEY not found in environment.`

## Notes

- no `.env` file was read
- no live provider was called
- this fix is intentionally narrow and does not change application runtime behavior

# Phase 22.5 v3 — Runtime Boot Matrix

| Component | Purpose | Safe Command | Port | Health Check | Required Env Names | Must Remain False Flags | Expected Success Signal | Evidence Artifact | Status | Blocker | Next Fix |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Backend API | FastAPI server | `cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000` | 8000 | `GET /health` -> 200 | DATABASE_URL (name only) | productionReady, liveProvidersEnabled | `{"status":"ok"}` | api_smoke_log | BLOCKED | Backend not started in this session | Start backend for API runtime |
| Frontend Dev Server | React SPA | `cd frontend && bun run dev` | 5173 | URL loads | — | — | 200 on localhost:5173 | browser_screenshots | BLOCKED | Pre-existing TS build error + frontend not started | Fix TS errors, start frontend |
| Database/Test DB | PostgreSQL | Docker compose | 5432 | pg_isready | DATABASE_URL (name only) | — | Connection accepted | db_smoke_log | BLOCKED | Docker not running | Start infra |
| Redis | Cache/queue | Docker compose | 6379 | ping PONG | REDIS_URL (name only) | — | PONG | redis_smoke_log | BLOCKED | Docker not running | Start infra |
| MCP Registry/Service | Tool registry | pytest | — | Service unit tests | — | — | Tests pass | mcp_test_log | SERVICE_PATH | No HTTP endpoint for MCP | None — service path is valid |
| Workflow Service | Draft workflow | pytest | — | Service unit tests | — | — | Tests pass | workflow_test_log | SERVICE_PATH | No HTTP endpoint for workflows | None — service path is valid |
| Beta Synthetic Tester | QA test infra | pytest | — | Unit tests | — | — | Tests pass | test_report | TEST_HARNESS | No runtime backend | Run tests |
| Browser Test Runner | Playwright | `npx playwright test` | — | Test execution | — | — | Tests pass/blocked | browser_trace | BLOCKED | No Playwright config found | Document exact blocker |
| API Smoke Scripts | HTTP smoke | bash/ps1 | 8000 | Endpoint response | — | — | Script output | api_smoke_log | BLOCKED | Backend not started | Start backend |
| Evidence Collector | Evidence storage | pytest | — | File output | — | — | Evidence files created | evidence_audit_report | TEST_HARNESS | No runtime to capture | Run tests |

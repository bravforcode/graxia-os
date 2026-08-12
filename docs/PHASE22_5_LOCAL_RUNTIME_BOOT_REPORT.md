# Phase 22.5 — Local Runtime Boot Report

## Status: COMMANDS DEFINED, NOT EXECUTED

Runtime boot controller scripts are defined but not executed in this terminal-only session.

## Boot Commands

| Component | Command | Status |
|---|---|---|
| Backend | `cd backend && uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level warning` | ⏳ Not started |
| Frontend | `cd frontend && bun run dev --port 5173` | ⏳ Not started (pre-existing TS error) |
| Database | Docker compose | ⏳ Not started |
| Redis | Docker compose | ⏳ Not started |

## Boot Controller Scripts

| Script | Purpose | Dry-Run Mode |
|---|---|---|
| `scripts/ai_tester_runtime_start.ps1` | Start backend/frontend | ✅ |
| `scripts/ai_tester_runtime_start.sh` | Start backend/frontend (Unix) | ✅ |
| `scripts/ai_tester_runtime_stop.ps1` | Stop backend/frontend | ✅ |
| `scripts/ai_tester_runtime_stop.sh` | Stop backend/frontend (Unix) | ✅ |
| `scripts/ai_tester_runtime_check.ps1` | Check running services | ✅ |
| `scripts/ai_tester_runtime_check.sh` | Check running services (Unix) | ✅ |

## Safety Checks

| Check | Status |
|---|---|
| No production DB connection | ✅ Scripts use localhost:8000 |
| No live provider flags | ✅ Scripts don't set env |
| No destructive commands | ✅ Validated by boot controller tests |
| Dry-run mode available | ✅ Scripts support --dry-run |

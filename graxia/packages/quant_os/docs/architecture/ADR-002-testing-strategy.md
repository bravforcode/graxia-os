# ADR-002: Testing Strategy

**Status:** Accepted · **Date:** 2026-06-25

## Context
The codebase has 247+ tests across unit, integration, drill, and chaos testing. Need a consistent strategy for what gets tested where.

## Decision
- **Unit tests** (`tests/`): Pure behavior, no MT5/Redis/DB — fast (<1s each)
- **Integration tests** (`canary/test_*`, `cost/test_*`): Module boundary, lightweight fixtures
- **Drill tests** (`canary/drills/`): Chaos engineering — verify failure modes
- **Phase tests** (`tests/test_phase_N_*`): End-to-end phase acceptance
- **Script tests** (`tests/test_*.py` run via `__main__`): Manual timing/load benchmarks

## Consequences
- CI runs unit + integration + phase tests: ~40s
- Backend tests (asyncpg/aiosqlite) need separate environment
- Quarantine manifest tracks known-failing tests with expiry

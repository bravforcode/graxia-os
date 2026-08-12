# ADR-003: Phase-Based Development

**Status:** Accepted · **Date:** 2026-06-25

## Context
The codebase was delivered in phases (BE-P0 through BE-P13, G0-G4). Need a standard for organizing future work.

## Decision
- **Naming**: `BE-P{number}` for backtest/execution phases, `G{number}` for governance/infrastructure
- **Each phase delivers**: source code + tests + evidence artifacts + STATUS.md entry
- **Phase size**: self-contained vertical slice (not horizontal layer)
- **Gate**: all tests pass before phase is considered complete
- **Quarantine**: failing tests get quarantine entry (not blocker), but must have expiry

## Consequences
- Easy to track progress: `grep "pass" tests/test_phase_*`
- New contributors can start with any phase
- Evidence artifacts live in `artifacts/` for audit trail

# ADR-006: Error Handling & Fail-Closed

**Status:** Accepted · **Date:** 2026-06-25

## Context
A trading system must never silently ignore errors that could lead to financial loss. Need consistent error handling across all risk-sensitive paths.

## Decision
- All validation gates are **fail-closed** (deny by default, require explicit approval)
- Unknown/unexpected states produce `CRITICAL_INCIDENT` events (not silent catch)
- Circuit breakers for external dependencies (Redis, MT5) — OPEN after N failures
- Kill switch can be triggered manually (API endpoint) or automatically (daily loss limit)
- Quarantine manifest for known test failures (no silent skips, has expiry)
- All exceptions are logged with structured context before re-raise

## Consequences
- Higher code verbosity but safer runtime behavior
- No silent fallbacks that mask bugs — every error has a paper trail
- Operators can audit decisions through ledger and incident logs

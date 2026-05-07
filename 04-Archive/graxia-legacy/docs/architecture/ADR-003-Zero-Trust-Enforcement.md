# ADR-003: Zero-Trust Enforcement & HR-10

## Status
Accepted

## Context
BravOS v3 Hard Rule 10 (HR-10) mandates that no internal communication happens without authentication.

## Decision
Enforce Zero-Trust via a "Security-First" Middleware in the `bravos_core` library.
- The middleware automatically decodes and validates incoming JWTs.
- It rejects any request without a valid token (except `/health` and `/docs`).
- It populates a global `request.state.user` object for downstream capability checks.

## Consequences
- Eliminates accidental exposure of internal endpoints.
- Simplifies agent development: security logic is handled by the core library.
- Direct alignment with Enterprise Compliance standards.

# ADR-002: Identity Broker & S2S Authentication

## Status
Accepted

## Context
In a multi-agent company mesh, agents and services must communicate securely without relying on network-level trust (which is easily spoofed).

## Decision
Implement a centralized **Identity Broker** service that issues short-lived JWT tokens.
- Every internal service call must include an `Authorization: Bearer <token>` header.
- Tokens are task-scoped: they contain `mission_id` and `task_id` to limit an agent's blast radius.
- The `bravos_core` package provides a standard middleware to verify these tokens.

## Consequences
- No service-to-service trust without an Identity-Broker-signed token.
- Increased observability via `trace_id` embedded in JWTs.
- Clear audit trail of which entity performed which action.

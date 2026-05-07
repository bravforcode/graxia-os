# ADR-001: Monorepo Standards

## Status
Accepted

## Context
BravOS v3 is a complex multi-agent system requiring shared protocols (BWCP) and various services (FastAPI, Next.js). We need a unified structure to manage dependencies and deployments.

## Decision
Adopt a Polyglot Monorepo structure:
- `apps/`: High-level user-facing applications and public gateways.
- `services/`: Specialized microservices (Identity, Risk, Agent Mesh).
- `packages/`: Shared libraries and protocols (Language-agnostic schemas).
- `tools/`: Operational scripts and compliance checkers.

## Consequences
- Shared schemas must be mirrored in both Pydantic (Python) and Zod (TS).
- Strict linting and Hard Rule checks are enforced at the root via Husky.
- Unified orchestration via Docker Compose and Makefile.

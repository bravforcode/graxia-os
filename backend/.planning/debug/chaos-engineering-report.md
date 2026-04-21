# Chaos Engineering / Resilience Report (2026-04-16)

## Baseline Verification (Repo-Level)

- `.\verify.ps1` (root): PASS
  - Backend: 82 passed, 10 skipped
  - Frontend: lint PASS, unit tests PASS, build PASS, Playwright E2E PASS, Storybook build PASS

## Fixes Applied

### 1) Python syntax bug affecting coverage + runtime safety

- Fixed invalid indentation that made `app/core/unit_of_work.py` syntactically invalid.
- Impact: coverage tooling and any import path referencing this module could fail.
- Verified: `python -m pytest tests -q` PASS and `--cov=app` PASS.

Files:
- `backend/app/core/unit_of_work.py`

### 2) Circuit Breaker async correctness

- Added an async-safe execution path so circuit breaker state transitions and failure counting happen after awaiting the wrapped coroutine.
- Added tests that validate OPEN → HALF_OPEN → CLOSED recovery flow for async calls.

Files:
- `backend/app/core/circuit_breaker.py`
- `backend/tests/test_chaos_resilience.py`

## Chaos / Fault-Injection Test Coverage Added

Added focused “failure mode” tests that intentionally simulate common production failures without performing destructive actions on external systems:

- Circuit breaker:
  - opens after threshold failures and blocks calls while OPEN
  - recovers after timeout for async calls
- Unit-of-work transaction safety:
  - rolls back on exception within context
  - rolls back and re-raises when commit fails
- Rate limiting under abusive patterns:
  - simulates repeated login attempts until the rate limiter blocks (429)

Files:
- `backend/tests/test_chaos_resilience.py`

## Operational Soak (Built-In)

The repository already contains a long-running “soak monitor” that samples system readiness continuously:

- Script: `backend/scripts/soak_monitor.py`
- Core: `backend/app/core/soak_monitor.py`

Example:
- One-shot check:
  - `python backend/scripts/soak_monitor.py --base-url http://localhost:8000 --once`
- 24h soak (default):
  - `python backend/scripts/soak_monitor.py --base-url http://localhost:8000 --hours 24 --interval-seconds 60`

## Notes on Full Chaos Engineering Scope

The following items require a controlled staging environment and infrastructure-level tooling; they cannot be safely or faithfully executed purely as unit/integration tests inside this repository:

- physical hardware swap / node replacement
- true network partition / packet loss / bandwidth throttling between services
- database failover, replica promotion, storage-level corruption simulation
- “DDoS simulation” beyond safe, authenticated, rate-limited load testing

Recommended approach for enterprise-grade chaos:

- Use staging + production-like topology (Docker/Kubernetes) with explicit blast-radius controls.
- Inject faults with dedicated tools (e.g., network toxics/proxies, traffic shaping, controlled process termination, DB primary failover drills).
- Run under SLO/SLA gates with rollback automation and audit logging enabled.

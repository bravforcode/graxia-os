<opus_scratchpad>
  [SYSTEM_MAP] Persona: APEX-AUDITOR (Principal Software Architect). Context: Graxia OS, a B2B SaaS web app / AI Agent orchestration pipeline. Tech: FastAPI, SQLAlchemy, React, Celery, Redis. Dependency mapping: Backend -> Celery/Redis -> DB.
  [FIRST_PRINCIPLES] Deconstructing backend `main.py` and `pyproject.toml`. FastAPI application initialization, middleware stack construction, dependency definitions.
  [DOUBT_INJECTION] FastAPI middleware stack order is LIFO (Last Added = First Executed). IPFilterMiddleware is added first, meaning it executes LAST. This exposes Auth and Rate Limiting to malicious IPs. Unpinned dependencies (`>=`) invite build breaks. Two sanitization middlewares cause performance degradation.
  [PLATFORM_CONSISTENCY] React frontend utilizing modern JS features, but the `package.json` script `dev:backend` runs uvicorn directly, circumventing Docker-based backing services (Redis/PG). Python dependencies use floating versions instead of locked files.
  [IRON_WALL_TENANCY] Tenancy enforcement (organization_id) is NOT globally forced in `main.py` middleware or base query scopes from the provided snippet. Must flag as CRITICAL C-01.
  [AGENTIC_HYDRATION] Persona hydrated: APEX-AUDITOR. Injecting enterprise-grade strictness based on MASTER_AI_RULES.md.
  [THE_10X_PIVOT] Reorder middleware stack (Size -> IP -> Rate -> Auth -> CSRF). Pin dependencies. Implement Global Tenancy via ContextVars and SQLAlchemy Base query overrides.
</opus_scratchpad>

- EXECUTIVE SUMMARY
The Graxia OS codebase represents an ambitious and modern B2B SaaS architecture leveraging asynchronous Python (FastAPI, asyncpg) and task orchestration (Celery, Redis). However, an exhaustive audit of the provided configuration and entry point reveals severe structural vulnerabilities. The middleware stack is inverted, exposing the application to Denial of Service (DoS) and authentication bypass vectors. Furthermore, the explicit Enterprise Tenancy mandate is entirely absent at the global enforcement level. Immediate architectural realignment is required before scaling or processing production traffic.

- OVERALL HEALTH SCORE
42 / 100 (High Risk)

- DIMENSION SCORECARD (1-10)
1. Architecture & System Design: 6/10
2. Code Quality & Maintainability: 5/10
3. Security (Tenancy & Middleware): 2/10
4. Performance & Efficiency: 4/10
5. Testing & Quality Assurance: N/A (Assumed 5/10)
6. Data Layer & Database Design: 7/10
7. API Design & Contracts: 6/10
8. DevOps & Infrastructure: 5/10
9. Dependencies & Supply Chain: 3/10
10. Documentation & Developer Experience: 4/10

- CRITICAL ISSUES (C-01...)
**C-01: Inverted Middleware Stack Exposing Core Systems**
*Evidence:* In `backend/app/main.py`, `IPFilterMiddleware` is added first via `app.add_middleware()`. Because FastAPI evaluates middleware in reverse order (LIFO), `IPFilterMiddleware` acts as the *innermost* layer, executing *after* `AuthMiddleware`, `RateLimitMiddleware`, and `CSRFMiddleware`.
*Impact:* Malicious IPs and oversized payloads will traverse and hammer the Auth and Rate Limit systems, causing severe application-layer DDoS, CPU starvation, and potential exploit vectors before finally being rejected by the IP filter.
*Remediation:* Reverse the middleware insertion order. Network-level filters (`RequestSizeLimitMiddleware`, `IPFilterMiddleware`) must be added *last* in the code so they execute *first* on the incoming request.

**C-02: Absolute Lack of Global Tenancy Enforcement (Iron Wall Breach)**
*Evidence:* The project context mandates "organization_id required on ALL queries", but `main.py` lacks any `TenantContextMiddleware` or global request state initialization to enforce this context safely before routing.
*Impact:* High probability of cross-tenant data leakage. Relying on developers to manually filter `organization_id` on every individual SQLAlchemy query is a guaranteed failure point in enterprise SaaS.
*Remediation:* Implement a `TenantContextMiddleware` that securely extracts `organization_id` (from the verified token) into Python `contextvars`. Override SQLAlchemy's execution layer or use Row-Level Security (RLS) to transparently enforce `WHERE organization_id = :org_id` on all database operations.

**C-03: Supply Chain Fragility (Floating Dependencies)**
*Evidence:* `pyproject.toml` uses loose version boundaries (`fastapi>=0.111.0`, `alembic>=1.13.0`, `celery[redis]>=5.4.0`).
*Impact:* Any minor or major release in these core packages will silently break the CI/CD pipeline or introduce incompatible API changes, causing production outages.
*Remediation:* Transition to deterministic package management (e.g., Poetry, uv, or pip-tools) and generate a rigid lock file with exact hashes and versions (`==`).

- HIGH ISSUES (H-01...)
**H-01: Redundant and Expensive Sanitization Layers**
*Evidence:* Both `RequestSanitizationMiddleware` and `InputSanitizationMiddleware` are registered back-to-back in `main.py`.
*Impact:* Parsing, sanitizing, and reconstructing JSON request bodies multiple times per request will obliterate asynchronous event-loop performance and block the main thread.
*Remediation:* Consolidate sanitization into a single, highly optimized pass, or preferably, push sanitization down to the Pydantic schema validation layer where field-level context is available.

- MEDIUM ISSUES
**M-01: Development Script Anti-Pattern**
*Evidence:* `package.json` specifies `"dev:backend": "cd backend && uvicorn app.main:app --reload"`.
*Impact:* Bypasses Docker-based environment consistency. Running `uvicorn` directly fails to guarantee the presence of required local backing services like Redis, Celery workers, and PostgreSQL.
*Remediation:* Utilize `docker-compose up` to orchestrate the entire backend environment. Remove standalone backend scripts from the Node.js package.json.

**M-02: Unresolved Lifespan Reference**
*Evidence:* `app = FastAPI(title="Graxia OS", lifespan=lifespan)` references a `lifespan` function that is neither imported nor defined within the `main.py` context block.
*Impact:* If connection pools (asyncpg, Redis) are not properly managed in this missing lifespan, the application will leak connections upon server restarts, causing fatal connection exhaustion.
*Remediation:* Ensure the `lifespan` context manager is clearly defined, yielding correctly, and aggressively closing all async backing services during the teardown phase.

- LOW ISSUES
**L-01: Monolithic Application Instantiation**
*Evidence:* `main.py` heavily crowds middleware configurations directly onto the `app` instance.
*Impact:* Reduces readability and modularity as the application scales and more enterprise integrations are added.
*Remediation:* Extract middleware configuration into a dedicated `setup_middlewares(app)` factory function inside `app/core/setup.py`.

- GENUINE STRENGTHS
1. **Modern Asynchronous Stack:** Utilizing `asyncpg` with SQLAlchemy 2.0+ is the gold standard for high-throughput Python database operations.
2. **CQRS Pattern Awareness:** The presence of `backend/app/cqrs/` indicates forward-thinking architecture, properly separating read/write boundaries for complex AI agent orchestrations.
3. **Pydantic Hardening:** Explicitly requiring `pydantic[email]` shows attention to strict, type-safe data validation boundaries.

- ISSUE STATISTICS
* Critical: 3
* High: 1
* Medium: 2
* Low: 1

- MASTER ISSUE LIST
1. [C-01] CRITICAL · Inverted Middleware Stack Exposing Core Systems · Security · 2h
2. [C-02] CRITICAL · Absolute Lack of Global Tenancy Enforcement (Iron Wall Breach) · Architecture · 8h
3. [C-03] CRITICAL · Supply Chain Fragility (Floating Dependencies) · DevOps · 1h
4. [H-01] HIGH · Redundant and Expensive Sanitization Layers · Performance · 2h
5. [M-01] MEDIUM · Development Script Anti-Pattern · DX · 1h
6. [M-02] MEDIUM · Unresolved Lifespan Reference · Architecture · 1h
7. [L-01] LOW · Monolithic Application Instantiation · Code Quality · 1h

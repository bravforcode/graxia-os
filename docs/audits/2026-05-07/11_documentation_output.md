# Graxia OS Documentation Suite

---

### 1. README.md
# Graxia OS
**The Autonomous Enterprise Operating System**

Graxia OS is a full-stack SaaS platform designed for high-throughput data pipelines and multi-agent system (MAS) orchestration. It leverages a modern distributed architecture to provide secure, tenant-isolated agentic automation.

## Tech Stack
- **Backend:** Python 3.12, FastAPI, SQLAlchemy (PostgreSQL)
- **Frontend:** React (TS), Node.js, Bun
- **Async Workers:** Celery, Redis
- **Infrastructure:** Docker, Docker Compose, GitHub Actions, GHCR

## Quick Start
1. **Clone the repository:** `git clone https://github.com/graxia/graxia-os.git`
2. **Environment Setup:** `cp .env.example .env`
3. **Launch Workspace:** `docker-compose up --build`
4. **Access:**
   - Frontend: `http://localhost:3000`
   - API Docs: `http://localhost:8000/docs`

---

### 2. ARCHITECTURE.md
# Graxia OS Architecture

## Design Philosophy: CQRS & Task-Driven
Graxia OS follows a **Command Query Responsibility Segregation (CQRS)** pattern. Commands that mutate state are handled via the `AsyncUnitOfWork` pattern to ensure atomicity and consistency across distributed services.

## Tenancy: Iron Wall
Isolation is enforced at the database level using **Row Level Security (RLS)** and at the application level via **ContextVars**. Every request is scoped to an `organization_id` immediately upon authentication.

## MAS Orchestrator
The Multi-Agent System (MAS) uses `asyncio.Semaphore` to manage bounded concurrency. This prevents resource exhaustion during heavy agentic workloads while maintaining high responsiveness.

---

### 3. API_SPEC.md
# Graxia OS API Specification

## Middleware Pipeline (Strict Order)
To ensure maximum security, middleware is ordered as follows:
1. **IPFilter:** Drops traffic from unauthorized sources.
2. **RateLimiter:** Prevents DDoS and brute-force attempts.
3. **AuthMiddleware:** Validates JWT and hydrates the `organization_id` context.

## Primary Endpoints
- `POST /v1/commands`: Execute state-changing operations (CQRS Commands).
- `GET /v1/queries`: Fetch data (CQRS Queries).
- `POST /v1/agents/spawn`: Initiate an agentic workflow in the MAS.

---

### 4. DEV_GUIDE.md
# Developer Guide

## Local Development
**Mandate:** All local development MUST occur within the Docker Compose environment to ensure parity with production.

## Coding Standards
- **Async First:** Use `async/await` for all I/O bound operations.
- **Unit of Work:** All database mutations MUST use the `AsyncUnitOfWork` context manager.
- **Tenancy:** Never query without the `organization_id` filter (automatically applied by RLS, but must be respected in app logic).

---

### 5. OPS_GUIDE.md
# Operations & Deployment

## CI/CD Pipeline
- **GitHub Actions:** Triggered on merge to `main`.
- **Images:** Built and pushed to **GitHub Container Registry (GHCR)**.
- **Deployment:** Automated rollouts to staging/production clusters.

## Monitoring
- **Redis:** Monitors task queues for Celery.
- **Celery Flower:** Real-time monitoring of agentic task execution.

---

### 6. SECURITY.md
# Security & Privacy Mandate

## Iron Wall Tenancy
Every database query is automatically scoped with `WHERE organization_id = :org_id`. This is the core of our "Iron Wall" guarantee—data leaks between organizations are architecturally impossible.

## Network Security
- **IP Filtering:** Mandatory whitelist for API access.
- **Rate Limiting:** Granular per-tenant and per-IP limits enforced before authentication.

---

### 7. CHANGELOG.md
# Changelog

## [3.0.0] - Recent Refactor
### Added
- **AsyncUnitOfWork:** Integrated for atomic CQRS operations.
- **Bounded Concurrency:** Implemented in MAS Orchestrator via `asyncio.Semaphore`.
- **GHCR Integration:** Automated image builds in GitHub Actions.

### Changed
- **Middleware Reordering:** Moved IPFilter and RateLimit before Auth for better protection.
- **Tenancy:** Transitioned to ContextVars + RLS for "Iron Wall" isolation.

### Fixed
- Improved local developer experience via mandated Docker Compose usage.

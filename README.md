# Graxia OS

**Your personal AI chief of staff.** Graxia OS finds leads, drafts outreach, manages approvals, tracks your revenue pipeline, and executes multi-agent tasks — autonomously, with human oversight at every decision point.

## Quickstart (local development)

```bash
git clone <repo-url>
cd "graxia os"
# Edit .env.development — at minimum set:
#   DATABASE_URL, SECRET_KEY, ADMIN_DEFAULT_EMAIL, ADMIN_DEFAULT_PASSWORD
# For offline dev without Postgres, add:
#   USE_SQLITE_FALLBACK=true

# Start the full stack (development mode)
docker compose --env-file .env.development -f config/docker-compose.dev.yml up
```

- Backend API: http://localhost:8000 (docs at `/docs`)
- Frontend: http://localhost:5173
- n8n: http://localhost:5678

For production deployment see [SETUP_GUIDE.md](SETUP_GUIDE.md) and [docs/SECRETS_MANAGEMENT.md](docs/SECRETS_MANAGEMENT.md).

---

Graxia OS คือ workspace สำหรับสร้าง Personal Sovereign OS: ระบบควบคุมงานหาโอกาส งาน outreach และ CRM ส่วนตัวที่ใช้ AI agents ช่วยค้นหา คัดกรอง จัดลำดับความสำคัญ ร่างข้อความ ติดตามผล และบันทึกความรู้ลง second brain โดยมีมนุษย์เป็นผู้อนุมัติการกระทำสำคัญก่อนส่งออกจริง

เป้าหมายของ repo นี้ไม่ใช่แค่ dashboard แต่เป็น control plane ที่รวม backend API, frontend operations UI, agent pipeline, job scheduler, integrations, monitoring และ production deployment path ไว้ในระบบเดียว

สถานะปัจจุบัน: repo นี้เป็น stabilized development baseline ที่ใช้งานและทดสอบเส้นทางหลักได้แล้ว แต่ยังไม่ควรถูกอ่านว่าเป็น production-readiness attestation แบบสมบูรณ์ งานที่ต้องตรวจจริงก่อนใช้งาน production คือ Docker stack บนเครื่องเป้าหมาย, credentials ของ external integrations, deployment/rollback จริง, และ audit เชิง runtime บนข้อมูลจริง

## Directory Structure

- `config/`: Centralized configuration files for Docker, PM2, and Redis.
- `scripts/`: Operational and deployment scripts.
- `frontend/`: React frontend application.
- `backend/`: FastAPI backend service.

## Project Goal

ระบบนี้ถูกออกแบบเพื่อช่วย operator คนเดียวให้ทำงานแบบทีมเล็กได้ โดยลดงานซ้ำและเพิ่มการมองเห็นของ pipeline งานทั้งหมด:

- ค้นหาโอกาสจากหลายแหล่ง เช่น freelance, competition, job board, network lead และ event
- ให้ AI วิเคราะห์ fit, risk, effort, timing, score และ next action
- เก็บสถานะของ opportunities, jobs, contacts, drafts, submissions, tasks และ email threads ใน API เดียว
- สร้าง draft สำหรับ proposal, follow-up, intro message และ briefing โดยยังมี approval gate
- ติดตามค่าใช้จ่าย LLM, quota, event bus, scraper health และ worker health
- sync โครงสร้างงานเข้ากับ Obsidian second brain เพื่อให้ project context, contacts, tasks และ reviews ไม่หลุดจากระบบความรู้
- รองรับ local development, Docker Compose และ always-on production stack ที่ใช้ Supabase เป็น PostgreSQL หลัก

## What This System Does

Graxia OS ทำงานเป็น loop แบบนี้:

1. Identity และ context ของ operator ถูกอ่านจาก `identity/` และ Obsidian vault ที่ตั้งค่าไว้
2. Scrapers และ scheduled jobs ดึง opportunities, job postings, inbox/calendar context และข้อมูลที่เกี่ยวข้อง
3. Agents วิเคราะห์ข้อมูล สร้าง score ตัดสินใจเชิงกลยุทธ์ และ publish domain events
4. Backend API บันทึก state ลง database ผ่าน SQLAlchemy models และเปิด surface ภายใต้ `/api/v1`
5. Celery workers ประมวลผลงาน background เช่น scan, briefing, follow-up, email processing, backup และ weekly review
6. Frontend React UI แสดง control plane สำหรับดู health, opportunities, drafts, jobs, contacts, tasks, costs, event bus และ settings
7. Integrations เช่น Google Workspace, Telegram, Obsidian, n8n และ monitoring stack เชื่อมระบบออกไปยังโลกจริง

ภาพรวม flow:

```text
External sources
  -> scrapers / Google Workspace / n8n / manual input
  -> FastAPI control plane
  -> agents + model router + event bus
  -> PostgreSQL / Supabase
  -> Celery queues and scheduled jobs
  -> React frontend, Telegram alerts, Obsidian second brain, metrics
```

## Current Verified Baseline

เส้นทางที่เป็น canonical ตอนนี้คือ React frontend ใน `frontend/` และ backend API ภายใต้ `/api/v1` เท่านั้น ส่วน `dashboard/` เป็น static legacy surface และไม่ได้ถูก mount โดย backend runtime

สิ่งที่ verified จากเอกสาร handoff และ scripts ปัจจุบัน:

- Backend import ได้ผ่าน `from app.main import app`
- Backend root `/` คืน API metadata ไม่ redirect ไป legacy dashboard
- Process health อยู่ที่ `GET /health`
- Application health อยู่ที่ `GET /api/v1/system/health`
- Prometheus metrics อยู่ที่ `GET /metrics`
- OpenAPI export ทำได้ผ่าน `cd backend && python scripts/export_openapi.py --output openapi.json`
- Backend canonical suite อยู่ที่ `backend/tests/`
- Legacy/generated tests ถูกเก็บไว้ที่ `backend/tests_legacy/` และไม่ใช่ acceptance suite ปัจจุบัน
- Frontend มี lint, unit tests, browser E2E, production build และ Storybook build scripts
- Obsidian automation มี bootstrap/sync สำหรับ second-brain workspace เมื่อ config พร้อม
- Windows verification entrypoint คือ `.\verify.ps1`
- CI workflow อยู่ที่ `.github/workflows/ci.yml`

## Tech Stack

Backend:

- FastAPI
- SQLAlchemy async
- Alembic
- PostgreSQL หรือ Supabase Postgres
- Redis (with caching layer)
- Celery และ Celery Beat
- JWT auth, cookie sessions, CSRF, rate limiting, security headers
- OpenClaw เป็น LLM path หลักตาม config ปัจจุบัน และ Gemini เป็น fallback/configurable route
- Sentry error tracking (optional)

Frontend:

- React 18
- TypeScript
- Vite
- Bun
- React Router
- TanStack Query
- Axios
- Zustand
- Storybook
- Vitest, Testing Library, jest-axe, Playwright

Infrastructure:

- Docker Compose สำหรับ local stack
- `docker-compose.supabase.yml` สำหรับ always-on production shape
- Caddy
- n8n
- Prometheus, Alertmanager, Grafana, Loki, Promtail, cAdvisor, node exporter, Redis exporter, Flower
- 5 Grafana dashboards (System, Application, Business, Celery, LLM Costs)
- 15+ alert rules (Critical, Warning, Performance)

## Repository Layout

```text
.
├── backend/                  FastAPI app, agents, API routes, models, migrations, tests
│   ├── app/
│   │   ├── agents/           AI agents for scanning, scoring, drafting, learning, sync
│   │   ├── api/              Canonical REST API route modules
│   │   ├── core/             auth, LLM routing, event bus, policies, monitoring, bootstrap
│   │   ├── cqrs/             command/query handlers
│   │   ├── integrations/     external integration clients
│   │   ├── middleware/       auth, CSRF, rate limit, request/security middleware
│   │   ├── models/           SQLAlchemy domain models
│   │   ├── schemas/          Pydantic request/response schemas
│   │   ├── scrapers/         opportunity/job source adapters
│   │   ├── services/         domain services
│   │   ├── tasks/            Celery tasks, queues, beat schedule, DLQ/backup jobs
│   │   └── telegram_bot/     Telegram control/alert surface
│   ├── alembic/              database migrations
│   ├── scripts/              verification, backup, restore, OpenAPI, preflight tools
│   ├── tests/                canonical backend tests
│   └── tests_legacy/         old/generated tests kept for reference
├── frontend/                 React/Vite control plane
│   ├── src/components/       layout and reusable UI primitives
│   ├── src/pages/            app pages for operations workflows
│   ├── src/contexts/         auth/session state
│   ├── src/hooks/            frontend hooks
│   ├── src/lib/              API client and shared utilities
│   └── src/store/            UI state
├── config/                   ✨ Configuration files (NEW)
│   ├── docker-compose.*.yml  Multiple Docker Compose configurations
│   ├── Dockerfile.*          Multiple Dockerfile variants
│   ├── ecosystem.config.*    PM2 configurations
│   ├── netlify.toml          Netlify deployment config
│   ├── otel-collector-config.yaml  OpenTelemetry config
│   ├── pyproject.toml        Python project config
│   ├── pytest.ini            Pytest configuration
│   ├── redis.conf            Redis configuration
│   └── requirements.*.txt    Python requirements variants
├── scripts/                  ✨ All scripts consolidated (NEW)
│   ├── deployment/           Deployment scripts
│   ├── ops/                  Operations and maintenance scripts
│   ├── tests/                Test utilities
│   ├── dev.ps1, dev.sh       Development startup scripts
│   ├── start.ps1, start.sh   Production startup scripts
│   ├── setup.sh              Setup and installation
│   └── preflight.py          Pre-flight checks
├── deploy/                   Caddy, monitoring, systemd, smoke/rollback/deploy scripts
├── docs/                     runbooks, deployment docs, route manifest, security notes
│   ├── archive/              ✨ Archived documentation (NEW)
│   │   ├── old-docs/         Old documentation files
│   │   └── old-guides/       Old setup and deployment guides
│   ├── audits/               Security audit reports
│   ├── CLEANUP_COMPLETION_REPORT.md  ✨ Cleanup report (NEW)
│   └── NEXT_STEPS.md         ✨ Next steps guide (NEW)
├── identity/                 operator profile, positioning, templates, project identity
├── n8n/                      bundled workflow definitions
├── dashboard/                legacy static dashboard, not mounted by backend runtime
├── reports/                  security baseline artifacts
├── docker-compose.yml        local development stack
├── docker-compose.supabase.yml
├── Makefile
└── .gitignore                ✨ Updated with comprehensive patterns
```

**Recent Changes (2026-05-08):**
- ✨ Created `config/` directory for all configuration files
- ✨ Created `scripts/` directory consolidating all scripts
- ✨ Created `docs/archive/` for old documentation
- ✨ Updated `.gitignore` with comprehensive patterns
- ✨ Removed cache and temp files
- ✨ Removed secrets from git tracking
- ✨ Cleaned up root directory (80+ → 64 items)

See [docs/CLEANUP_COMPLETION_REPORT.md](docs/CLEANUP_COMPLETION_REPORT.md) for details.

## Backend Architecture

The backend is the canonical source of truth. `backend/app/main.py` creates the FastAPI app, starts runtime services in lifespan, wires the event handlers, optionally starts the embedded scheduler in development, bootstraps Obsidian when enabled, and mounts the route modules.

Important backend layers:

- `app/api`: HTTP boundary for auth, opportunities, drafts, contacts, jobs, tasks, costs, events, scrapers, system operations, approvals, integrations and admin routes
- `app/models`: persisted domain state such as users, opportunities, contacts, drafts, submissions, jobs, email threads, assistant tasks, usage, audit logs and scraper health
- `app/agents`: business automation layer that uses identity context, LLM routing and event publication
- `app/core/event_bus.py`: in-process event queue, event stats and failed-event capture/replay support
- `app/tasks`: Celery task definitions, queue routing, beat schedule, backup/restore drill, DLQ checks and autonomous recurring work
- `app/core/model_router.py`: routes task classes across cheap/mid/high model tiers with cost estimation
- `app/core/health_checker.py` and `app/core/runtime_state.py`: degraded/ready/blocked runtime reporting
- `app/middleware`: security headers, request size limit, input sanitization, rate limiting, auth and CSRF

Runtime startup behavior:

- validates production configuration when `APP_ENV=production`
- connects Redis when available
- starts event bus processing
- wires domain event handlers
- starts embedded scheduler only when enabled and not under pytest
- bootstraps Obsidian second brain when `OBSIDIAN_AUTO_BOOTSTRAP=true`
- sets runtime readiness state based on system checks

## Agent System

All agents inherit shared behavior from `BaseAgent`: access to identity context, the shared LLM client, the event bus, and audit logging.

Agent groups in this repo:

- Tactical agents: discover, score and prioritize opportunities
- Executive agents: decisioning, approval flow, brief generation and strategic recommendations
- Drafting/follow-up agents: prepare content and manage outreach continuation
- Learning agents: capture playbooks, analyze failures and improve future scoring
- Specialized agents: job hunting, email management, network building, personal assistant and Obsidian sync
- Analysis agents: strategy and compound decision support

Current agent files include:

```text
competition_scout.py
lead_hunter.py
job_hunter.py
scorer.py
decision_engine.py
drafter.py
briefer.py
follow_up.py
email_manager.py
network_builder.py
personal_assistant.py
learning_engine.py
playbook_capture.py
failure_analysis.py
strategy_agent.py
compound_engine.py
obsidian_sync.py
```

The intended rule is simple: agents can suggest, prepare and queue work, but important external actions should pass through approval or operator-visible controls.

## Frontend Architecture

The frontend in `frontend/` is a React SPA served by Vite in development and built as static assets for production.

Primary app routes:

```text
/login
/register
/
/opportunities
/drafts
/contacts
/metrics
/jobs
/emails
/tasks
/costs
/event-bus
/settings
```

The API client defaults to `/api/v1`, so local Vite uses a proxy to the backend:

```ts
VITE_DEV_PROXY_TARGET=http://localhost:8000
```

In Docker Compose the frontend container uses:

```text
VITE_DEV_PROXY_TARGET=http://backend:8000
```

Frontend responsibilities:

- authenticate users and maintain session through backend cookies/token flow
- protect app routes from unauthenticated access
- display operational health and degraded states
- list and act on opportunities, drafts, jobs, contacts, tasks and email threads
- expose cost, event bus and scraper status
- provide reusable UI primitives with Storybook coverage
- keep dev server on port `5173`

## Data Model Areas

The domain model is organized around operational state:

- `User`: authentication and role
- `Opportunity`: discovered opportunity with score, status, decision and metadata
- `JobPosting`: job/freelance lead with skill matching and status
- `Contact`: CRM entity for people and organizations
- `ContentDraft`: generated or prepared outreach content
- `Submission`: submitted proposals/applications and outcome tracking
- `EmailThread` and `EmailMessage`: inbox triage and communication state
- `AssistantTask`: work queue visible to operator
- `ApprovalRequest`: approval gate for risky or external actions
- `AutomationRun`: background run history
- `AuditLog`: compliance/debug trail
- `OpenClawUsage`: LLM usage and cost tracking
- `ScraperRun` and `ScraperHealth`: source reliability and ingestion tracking
- `SkillProfile`, `IdentitySnapshot`, `NetworkInteraction`, `OutcomePattern`: learning and personalization state

PostgreSQL/Supabase is the production target. SQLite appears only in the current deterministic canonical backend test harness; new persistence or integration behavior should still be verified against PostgreSQL/Supabase before production use.

## Scheduled Automation

Celery Beat owns recurring automation in the production stack. Do not run both embedded backend scheduler and Celery Beat in production.

Current beat schedule includes:

- daily database backup
- weekly restore drill
- DLQ depth check every 15 minutes
- daily scan
- morning briefing
- follow-up check
- job discovery twice daily
- email processing every 30 minutes
- weekly review
- weekly strategy
- monthly identity snapshot
- Obsidian daily note
- Obsidian refresh
- Redis backup

Queue split:

```text
critical    backups, restore drills, DLQ checks
default     scans, briefs, follow-ups, job discovery, weekly strategy/review
background  email processing, Obsidian refresh, Redis backup
dlq         failed/dead-letter work
```

## API Surface

Interactive docs are available in development at:

```text
http://localhost:8000/docs
```

Generated spec:

```text
backend/openapi.json
```

Regenerate it:

```bash
cd backend
python scripts/export_openapi.py --output openapi.json
```

Important root endpoints:

```text
GET /                  API metadata
GET /health            process/readiness health
GET /metrics           Prometheus metrics
GET /docs              Swagger UI in development
GET /openapi.json      OpenAPI JSON in development
```

Primary `/api/v1` groups:

```text
/api/v1/auth
/api/v1/admin
/api/v1/approvals
/api/v1/calendar
/api/v1/cognitive
/api/v1/commands
/api/v1/contacts
/api/v1/costs
/api/v1/drafts
/api/v1/email-threads
/api/v1/events
/api/v1/inbox
/api/v1/integrations/google
/api/v1/jobs
/api/v1/metrics
/api/v1/opportunities
/api/v1/runs
/api/v1/scrapers
/api/v1/skills
/api/v1/submissions
/api/v1/system
/api/v1/tasks
```

Obsidian routes are mounted at:

```text
/obsidian/health
/obsidian/bootstrap
/obsidian/sync
/obsidian/context
/obsidian/daily-note
/obsidian/weekly-review
```

Canonical response shapes:

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "token_type": "bearer",
  "user": {
    "id": "...",
    "email": "operator@example.com",
    "full_name": "Operator",
    "role": "user",
    "is_active": true,
    "created_at": "..."
  }
}
```

```json
{
  "total": 1,
  "items": []
}
```

## Environment Variables

Start from:

```bash
cp .env.example .env
```

Minimum local development values:

```bash
DATABASE_URL=postgresql+asyncpg://personal_os:changeme_in_production@localhost:5432/personal_os
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
SECRET_KEY=replace-with-a-long-random-secret
ENCRYPTION_KEY=replace-with-a-32-byte-compatible-key
ALLOWED_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
APP_BASE_URL=http://localhost:8000
FRONTEND_URL=http://localhost:5173
APP_ENV=development
```

Recommended optional values:

```bash
OPENCLAW_API_KEY=...
GEMINI_API_KEY=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REFRESH_TOKEN=...
GOOGLE_WORKSPACE_EMAIL=...
SERPAPI_KEY=...
```

Obsidian:

```bash
OBSIDIAN_VAULT_PATH=C:/Users/YourName/C:/Users/menum/OneDrive/Documents/Gracia
OBSIDIAN_ROOT_FOLDER=Second Brain
OBSIDIAN_AUTO_BOOTSTRAP=true
OBSIDIAN_AUTO_SYNC_ENABLED=true
OBSIDIAN_API_URL=http://localhost:27123
OBSIDIAN_API_KEY=
```

Important production behavior:

- `APP_ENV=production` enables strict bootstrap validation
- production rejects placeholder secrets, weak JWT signing keys, localhost URLs, missing backup config and missing control-plane credentials
- set `REQUIRE_SUPABASE=true` in the Supabase production stack
- keep `SCHEDULER_EMBEDDED=false` in production so only Celery Beat runs scheduled work

## Local Development

Prerequisites:

- Python 3.11 or 3.12
- Bun
- Docker Compose
- Git Bash on Windows if you want `verify.ps1` to validate shell scripts

Create `.env`:

```bash
cp .env.example .env
```

Start local Postgres and Redis:

```bash
make infra-up
```

Run migrations from the host:

```bash
make migrate-local
```

Start backend:

```bash
make run-local
```

Start frontend in another terminal:

```bash
make frontend-dev
```

Open:

```text
Frontend:    http://localhost:5173
Backend API: http://localhost:8000/docs
Health:      http://localhost:8000/health
App health:  http://localhost:8000/api/v1/system/health
```

## Docker Compose Development

Bring up the default stack:

```bash
make up
```

Run migrations inside the backend container:

```bash
make migrate
```

Check backend logs:

```bash
make logs
```

Run smoke tests against the running stack:

```bash
make smoke
```

Stop:

```bash
make down
```

Default `docker-compose.yml` includes:

- local Postgres
- Redis
- backend
- Celery worker
- Celery Beat
- frontend Vite dev server on port `5173`
- Ollama service profile for local LLM experiments
- n8n on port `5678`

## Supabase Always-On Production

Production path uses `docker-compose.supabase.yml` and Supabase as PostgreSQL source of truth.

First-time setup:

```bash
cp .env.production.template .env.production
```

Fill every placeholder in `.env.production`. Production startup is intentionally strict.

Then:

```bash
make supabase-preflight
make supabase-prod-migrate
make supabase-prod-up
```

Production runtime shape:

- Caddy terminates TLS and routes frontend, API, health, n8n and webhooks
- frontend serves built static assets
- backend runs FastAPI with strict production config
- Redis is local to the stack for broker/cache/rate limits/beat locks
- workers are split into `worker-critical`, `worker-default` and `worker-background`
- `beat` is the only scheduler
- Telegram bot runs as a separate service when configured
- n8n imports bundled workflows before start
- monitoring stack runs internally

Verify production target:

```bash
curl -fsS https://$APP_HOST/health
curl -fsS https://$APP_HOST/api/v1/system/health
python deploy/scripts/smoke_test.py --target "https://$APP_HOST"
```

Detailed runbook:

```text
docs/SUPABASE_PRODUCTION.md
```

## Verification

Full Windows verification:

```powershell
.\verify.ps1
```

Make verification:

```bash
make verify
```

Backend only:

```bash
cd backend
python -c "from app.main import app; print(app.title)"
python scripts/alembic_safe.py heads
python -m pytest tests -q
python scripts/export_openapi.py --output openapi.json
```

Frontend only:

```bash
cd frontend
bun run lint
bun run test
bun run test:e2e
bun run build
bun run build-storybook
```

Shell/script checks:

```bash
bash -n setup.sh
bash -n scripts/ops/backup_database.sh
bash -n scripts/ops/restore_database.sh
bash -n scripts/ops/smoke_tests.sh
```

## Test Policy

Use `backend/tests/` as the canonical backend suite.

Use `backend/tests_legacy/` only as historical/reference material. Many files there target old agent internals, stale endpoint shapes or external workflow assumptions and should not block current work unless they are intentionally rewritten against the current `/api/v1` contract.

Frontend verification should include lint, unit tests, build and browser E2E for changes touching user flows.

For database-sensitive changes:

- verify Alembic migrations
- verify PostgreSQL/Supabase behavior before production use
- do not rely on mocked persistence for production claims
- export OpenAPI after API schema changes

## Security Model

Security controls currently include:

- JWT access and refresh flow
- auth middleware on protected API routes
- CSRF protection for mutating requests
- rate limiting
- request size limits
- input sanitization middleware
- security headers
- role-based expectations in the route manifest
- audit logs for agent/system actions
- production bootstrap validation for secrets and URLs
- cost ceilings for LLM usage
- approval gates for risky/operator actions

Route control metadata is generated into:

```text
docs/route-manifest.json
```

## Operations

Primary health checks:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/system/health
curl http://localhost:8000/api/v1/costs/summary
curl http://localhost:8000/api/v1/scrapers/health
curl http://localhost:8000/api/v1/events/health
curl http://localhost:8000/metrics
```

Common operational docs:

```text
backend/OPERATIONAL_RUNBOOK.md
docs/LOCAL_STARTUP.md
docs/DEPLOYMENT.md
docs/TROUBLESHOOTING.md
docs/SUPABASE_PRODUCTION.md
docs/runbooks/
```

Backup and restore scripts:

```bash
bash scripts/ops/backup_database.sh
bash scripts/ops/restore_database.sh backups/backup_YYYYMMDD_HHMMSS.sql.gz
```

## Development Rules

- Treat `backend/app/main.py` and `/api/v1` as the canonical backend surface
- Do not revive `dashboard/` unless explicitly migrating it
- Keep frontend development on port `5173`
- Update `backend/openapi.json` after route/schema changes
- Keep migrations deterministic and review destructive operations with `scripts/ops/check_destructive_migrations.py`
- Keep Redis optional enough for degraded local startup, but required for full worker/scheduler behavior
- Keep PostgreSQL/Supabase as the production data target
- Avoid external calls in import-time tooling; integrations should initialize lazily when possible
- Prefer approval-first behavior for outward actions like sending messages, applying, or mutating external systems

## Known Follow-Ups

- Complete live Docker stack verification on a machine with Docker engine running
- Verify Google Workspace with real OAuth credentials
- Verify Telegram bot with real bot token and chat ID
- Verify live LLM path with valid OpenClaw/Gemini credentials
- Validate Supabase production deployment, rollback and restore drill on the real target host
- Broaden authenticated visual E2E coverage on a live stack
- Run live accessibility and Lighthouse audits against the deployed app
- Continue rewriting or deleting `backend/tests_legacy/` as old workflows are brought under the canonical contract
- Normalize remaining legacy timestamp helpers and Pydantic configuration warnings where they still exist

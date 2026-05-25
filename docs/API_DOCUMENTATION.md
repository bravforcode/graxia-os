# API Documentation

Canonical API documentation for the current backend lives in two places:

- Interactive docs: `http://localhost:8000/docs`
- Generated OpenAPI spec: `backend/openapi.json`

Regenerate the OpenAPI file from code:

```bash
cd backend
python scripts/export_openapi.py --output openapi.json
```

This Markdown file is intentionally concise. It lists the verified route groups mounted by `app.main` and points engineers to the generated OpenAPI spec for exact schemas.

## Base URLs

- App root: `http://localhost:8000`
- Versioned API prefix: `http://localhost:8000/api/v1`

## Health and Monitoring

- `GET /health`
- `GET /metrics`
- `GET /api/v1/system/health`
- `GET /api/v1/system/costs`
- `GET /api/v1/system/scraper-health`
- `GET /api/v1/events/health`
- `GET /api/v1/events/stats`
- `GET /api/v1/scrapers/health`
- `GET /api/v1/scrapers/stats`
- `GET /api/v1/costs/summary`
- `GET /api/v1/costs/usage`
- `GET /api/v1/costs/forecast`

## Auth

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `PUT /api/v1/auth/me`
- `POST /api/v1/auth/change-password`

## Core Product Routes

### Opportunities

- `GET /api/v1/opportunities`
- `GET /api/v1/opportunities/high-score`
- `GET /api/v1/opportunities/{opp_id}`
- `PATCH /api/v1/opportunities/{opp_id}/approve`
- `PATCH /api/v1/opportunities/{opp_id}/skip`

### Jobs

- `GET /api/v1/jobs`
- `GET /api/v1/jobs/stats`
- `GET /api/v1/jobs/{job_id}`
- `PATCH /api/v1/jobs/{job_id}/status`

### Contacts

- `GET /api/v1/contacts`
- `POST /api/v1/contacts`
- `GET /api/v1/contacts/{contact_id}`

### Submissions

- `GET /api/v1/submissions`
- `POST /api/v1/submissions`
- `PATCH /api/v1/submissions/{sub_id}/mark-won`
- `PATCH /api/v1/submissions/{sub_id}/mark-lost`

### Drafts

- `GET /api/v1/drafts`
- `GET /api/v1/drafts/{draft_id}`
- `PATCH /api/v1/drafts/{draft_id}/approve`
- `PATCH /api/v1/drafts/{draft_id}/reject`

### Skills

- `GET /api/v1/skills`
- `POST /api/v1/skills/bootstrap`

### Runs

- `GET /api/v1/runs`
- `GET /api/v1/runs/{run_id}`

### Tasks

- `GET /api/v1/tasks/`
- `POST /api/v1/tasks/`
- `GET /api/v1/tasks/stats`
- `GET /api/v1/tasks/stats/summary`
- `GET /api/v1/tasks/{task_id}`
- `PATCH /api/v1/tasks/{task_id}`
- `PATCH /api/v1/tasks/{task_id}/complete`
- `POST /api/v1/tasks/{task_id}/complete`
- `DELETE /api/v1/tasks/{task_id}`

### Email Threads

- `GET /api/v1/email-threads/`
- `GET /api/v1/email-threads/stats`
- `GET /api/v1/email-threads/stats/summary`
- `GET /api/v1/email-threads/{thread_id}`
- `GET /api/v1/email-threads/{thread_id}/messages`
- `PATCH /api/v1/email-threads/{thread_id}/mark-read`
- `POST /api/v1/email-threads/{thread_id}/mark-read`

## Operations and Control Plane

### Approvals

- `GET /api/v1/approvals`
- `GET /api/v1/approvals/{approval_id}`
- `PATCH /api/v1/approvals/{approval_id}/approve`
- `PATCH /api/v1/approvals/{approval_id}/reject`
- `PATCH /api/v1/approvals/batch/{batch_key}/approve`
- `PATCH /api/v1/approvals/batch/{batch_key}/reject`

### Commands and Cognitive State

- `POST /api/v1/commands/execute`
- `GET /api/v1/cognitive/today`
- `POST /api/v1/cognitive/checkin`
- `GET /api/v1/calendar/today`
- `GET /api/v1/inbox/triage`

### Strategy and Admin

- `GET /api/v1/system/weights`
- `POST /api/v1/system/weights/rollback`
- `GET /api/v1/system/audit-log`
- `POST /api/v1/system/reload-identity`
- `GET /api/v1/system/strategy`
- `POST /api/v1/system/scan`
- `POST /api/v1/system/scan/now`
- `POST /api/v1/system/brief`
- `POST /api/v1/system/brief/now`

### Events

- `GET /api/v1/events/stats`
- `GET /api/v1/events/failed`
- `POST /api/v1/events/replay/{index}`
- `DELETE /api/v1/events/failed/{index}`
- `DELETE /api/v1/events/failed`

### Metrics and Learning

- `GET /api/v1/metrics`
- `GET /api/v1/metrics/current-week`
- `GET /api/v1/metrics/history`
- `GET /api/v1/metrics/loss-analysis`

## Integrations

### Google Workspace

- `GET /api/v1/integrations/google/health`
- `GET /api/v1/integrations/google/gmail/inbox-summary`
- `GET /api/v1/integrations/google/calendar/today`

## Notes

- `/metrics` is the Prometheus endpoint and is mounted at the app root, not under `/api/v1`.
- `email-threads`, `tasks`, `events`, `costs`, and `scrapers` already include `/api/v1` in their router prefixes, so the exposed paths above are the canonical ones.
- If an example payload is needed, use `backend/openapi.json` or `/docs` instead of extending this file by hand.

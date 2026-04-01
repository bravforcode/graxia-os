# Personal Sovereign Enterprise OS v3

Autonomous background engine that finds clients, competitions, grants, and startup opportunities 24/7 — while protecting your time, reputation, and mental health.

## Quick Start

```bash
# 1. Copy and configure environment
cp .env.example .env
# Edit .env with your API keys (Gemini, Telegram)

# 2. Start all services
make up

# 3. Run database migrations
make migrate

# 4. Check health
make health
```

## Architecture

**Layer 1 — Tactical Engine:** Finds, scores, drafts  
**Layer 2 — Executive Intelligence:** Decides, strategizes, adapts to your state  
**Layer 3 — Self-Improving Core:** Learns from wins/losses, evolves over time

## Services

| Service | URL | Purpose |
|---------|-----|---------|
| Backend API | http://localhost:8000 | FastAPI + agents |
| Dashboard | http://localhost:8000/dashboard | Personal command center |
| API Docs | http://localhost:8000/docs | Swagger UI |
| n8n | http://localhost:5678 | Workflow automation |

## Tech Stack

- **Backend:** Python 3.12 + FastAPI + SQLAlchemy
- **Database:** PostgreSQL 15
- **Queue:** Redis + Celery
- **AI:** Gemini 2.0 Flash (free tier)
- **Notifications:** Telegram Bot
- **Dashboard:** HTML + Tailwind CSS

## Principles

1. Nothing goes to any external person without your approval
2. Max 5 actionable items surfaced per day
3. System runs under $0/month AI cost (Gemini free tier)
4. Every decision is logged and auditable

# 🚀 New Features Guide - Personal AI Assistant Integration

Complete guide to the new features added in v3.1.0

---

## 📋 Table of Contents

1. [Job Hunter Agent](#job-hunter-agent)
2. [Network Builder Agent](#network-builder-agent)
3. [Email Manager Agent](#email-manager-agent)
4. [Personal Assistant Agent](#personal-assistant-agent)
5. [OpenClaw Integration](#openclaw-integration)
6. [New API Endpoints](#new-api-endpoints)
7. [Scheduled Tasks](#scheduled-tasks)
8. [Configuration](#configuration)

---

## 🎯 Job Hunter Agent

Automatically discovers job opportunities from multiple platforms.

### Features
- Multi-platform scraping (LinkedIn, Upwork, Fiverr, Fastwork, DevPost)
- AI-powered fit scoring (0-10)
- Skill gap analysis
- Automatic deduplication
- Event-driven notifications

### Usage

```python
from app.agents.job_hunter import job_hunter_agent

# Run job discovery
result = await job_hunter_agent.run()
# Returns: {"discovered": 25, "new": 20, "duplicates": 5}

# Get top jobs
top_jobs = await job_hunter_agent.get_top_jobs(limit=10, min_score=7.0)

# Get statistics
stats = await job_hunter_agent.get_stats()
```

### API Endpoints

```bash
# Get all jobs
GET /api/v1/jobs?status=discovered&limit=50

# Get job by ID
GET /api/v1/jobs/{job_id}

# Get job statistics
GET /api/v1/jobs/stats
```

### Scheduled Execution
- Runs 2x per day (10 AM, 6 PM Bangkok time)
- Target: 50+ jobs/week
- Automatic notifications for high-scoring jobs

---

## 👥 Network Builder Agent

Discovers and manages professional contacts with AI-powered insights.

### Features
- LinkedIn profile scraping
- Contact value scoring (0-10)
- Relationship strength tracking
- Personalized outreach generation
- Interaction logging

### Usage

```python
from app.agents.network_builder import network_builder_agent

# Discover contacts from LinkedIn search
result = await network_builder_agent.discover_contacts(
    search_url="https://linkedin.com/search/results/people/?keywords=python+developer",
    max_contacts=10
)

# Generate personalized outreach
message = await network_builder_agent.generate_outreach(
    contact_id="uuid-here",
    context="Interested in collaboration on AI projects"
)

# Get top contacts
top_contacts = await network_builder_agent.get_top_contacts(limit=10, min_score=7.0)
```

### API Endpoints

```bash
# Get all contacts
GET /api/v1/contacts?limit=50

# Get contact by ID
GET /api/v1/contacts/{contact_id}

# Get contact statistics
GET /api/v1/contacts/stats
```

### Rate Limits
- LinkedIn: 20 requests/day (via OpenClaw)
- Automatic rate limit warnings at 80%

---

## 📧 Email Manager Agent

Intelligent email management with categorization and action item extraction.

### Features
- Gmail integration (fetch, parse)
- AI categorization (urgent, important, normal, spam, newsletter)
- Priority scoring (1-10)
- Action item extraction
- Email threading
- Auto-reply draft generation

### Usage

```python
from app.agents.email_manager import email_manager_agent

# Process unread emails
result = await email_manager_agent.fetch_and_process(
    max_emails=50,
    query="is:unread"
)
# Returns: {"processed": 45, "categorized": {...}, "action_items_created": 12}
```

### API Endpoints

```bash
# List email threads
GET /api/v1/email-threads?category=urgent&unread_only=true

# Get thread details
GET /api/v1/email-threads/{thread_id}

# Get thread messages
GET /api/v1/email-threads/{thread_id}/messages

# Mark as read
POST /api/v1/email-threads/{thread_id}/mark-read

# Get email statistics
GET /api/v1/email-threads/stats/summary
```

### Scheduled Execution
- Runs every 30 minutes (9 AM - 6 PM)
- Automatic alerts for urgent emails

### Email Categories

| Category | Description | Priority |
|----------|-------------|----------|
| urgent | Requires immediate action | 9 |
| important | High-value (jobs, clients, networking) | 7 |
| normal | Regular correspondence | 5 |
| newsletter | Newsletters, updates | 3 |
| spam | Promotional, marketing | 1 |

---

## 🤖 Personal Assistant Agent

Central coordinator providing daily briefings and system monitoring.

### Features
- Daily briefing generation
- Task management
- Cost monitoring and alerts
- Notification rate limiting (max 10/hour)
- System health monitoring
- Telegram integration

### Usage

```python
from app.agents.personal_assistant import personal_assistant_agent

# Generate daily briefing
briefing = await personal_assistant_agent.generate_daily_briefing()

# Send notification
success = await personal_assistant_agent.send_notification(
    message="Important update!",
    priority="urgent"
)

# Get system status
status = await personal_assistant_agent.get_system_status()
```

### Daily Briefing Includes

1. **Top 5 Jobs** - Highest-scored opportunities
2. **Urgent Tasks** - Overdue and due soon
3. **Important Emails** - Urgent and important unread
4. **Top Contacts** - Contacts to reach out to
5. **Yesterday's Activity** - Jobs, contacts, tasks completed
6. **Cost Summary** - Daily and monthly costs
7. **Recommendations** - AI-powered suggestions

### Scheduled Execution
- Morning briefing: 8:00 AM daily
- Sent via Telegram

---

## 🌐 OpenClaw Integration

Browser automation and advanced web scraping.

### Features
- Full browser automation
- Redis caching (4h TTL)
- Rate limiting per platform
- Cost tracking and budget alerts
- Exponential backoff retry
- Fallback mechanisms

### Usage

```python
from app.core.openclaw import openclaw_client

# Scrape URL
result = await openclaw_client.scrape_url(
    url="https://example.com",
    platform="linkedin",
    wait_for_selector=".profile-card",
    use_cache=True
)

# Extract contacts
contacts = await openclaw_client.extract_contacts(
    url="https://linkedin.com/search/...",
    platform="linkedin"
)

# Extract jobs
jobs = await openclaw_client.extract_jobs(
    url="https://upwork.com/search/...",
    platform="upwork"
)

# Health check
health = await openclaw_client.health_check()

# Usage statistics
stats = await openclaw_client.get_usage_stats(days=7)
```

### Rate Limits

| Platform | Limit | Cost per Request |
|----------|-------|------------------|
| LinkedIn | 50/day | $0.10 |
| Network | 20/day | $0.10 |
| Default | 100/day | $0.10 |

### Budget Controls
- Daily budget: $1.67 (~$50/month)
- Monthly budget: $50
- Automatic alerts at 80%
- Hard stop at 100%

---

## 🔌 New API Endpoints

### Tasks API

```bash
# List tasks
GET /api/v1/tasks?status=pending&priority_min=7

# Get task
GET /api/v1/tasks/{task_id}

# Create task
POST /api/v1/tasks
{
  "title": "Send proposal",
  "priority": 8,
  "due_date": "2024-01-20T10:00:00Z"
}

# Update task
PATCH /api/v1/tasks/{task_id}
{
  "status": "in_progress"
}

# Complete task
POST /api/v1/tasks/{task_id}/complete

# Delete task
DELETE /api/v1/tasks/{task_id}

# Task statistics
GET /api/v1/tasks/stats/summary
```

### Costs API

```bash
# Cost summary
GET /api/v1/costs/summary
# Returns: today, week, month costs with budgets

# Usage history
GET /api/v1/costs/usage?platform=linkedin&days=7

# Cost forecast
GET /api/v1/costs/forecast
# Returns: forecasted monthly cost based on current usage
```

### Email Threads API

See [Email Manager Agent](#email-manager-agent) section above.

---

## ⏰ Scheduled Tasks

All tasks run automatically via APScheduler.

### Schedule

| Task | Schedule | Description |
|------|----------|-------------|
| Daily Scan | 7:00 AM | Scan opportunities |
| Morning Briefing | 8:00 AM | Daily briefing |
| Follow-up Check | 9:00 AM | Check follow-ups |
| Email Processing | Every 30 min (9 AM - 6 PM) | Process emails |
| Job Discovery | 10 AM, 6 PM | Discover jobs |
| Weekly Strategy | Sunday 8:30 AM | Strategy review |
| Weekly Learning | Sunday 9:30 AM | Learning review |
| Identity Snapshot | 1st of month 10 AM | Identity backup |

### Manual Execution

```python
# Run job discovery manually
from app.tasks.job_discovery import run_job_discovery
await run_job_discovery()

# Run email processing manually
from app.tasks.email_processing import run_email_processing
await run_email_processing()

# Send morning briefing manually
from app.tasks.morning_briefing import send_morning_briefing
await send_morning_briefing()
```

---

## ⚙️ Configuration

### Environment Variables

Add to `.env`:

```bash
# OpenClaw (required for LinkedIn, Upwork, Fiverr)
OPENCLAW_API_KEY=your_openclaw_api_key
OPENCLAW_BASE_URL=https://api.openclaw.ai/v1

# Gmail (required for Email Manager)
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REFRESH_TOKEN=your_google_refresh_token
GOOGLE_WORKSPACE_EMAIL=your_email@gmail.com

# Telegram (required for notifications)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
TELEGRAM_POLLING_ENABLED=true

# Cost Controls
MAX_DAILY_AI_COST_USD=1.67
MAX_MONTHLY_AI_COST_USD=50.00
MAX_OUTREACH_PER_DAY=5
MAX_PENDING_APPROVALS=10
```

### Database Migrations

Run migrations to create new tables:

```bash
cd backend
alembic upgrade head
```

### Verify Setup

```bash
# Check system health
curl http://localhost:8000/health

# Check OpenClaw integration
curl http://localhost:8000/api/v1/integrations/openclaw/health

# Check Gmail integration
curl http://localhost:8000/api/v1/integrations/gmail/health

# Check cost summary
curl http://localhost:8000/api/v1/costs/summary
```

---

## 🎯 Quick Start

### 1. Configure API Keys

Edit `.env` with your API keys (see Configuration section).

### 2. Run Migrations

```bash
cd backend
alembic upgrade head
```

### 3. Start Services

```bash
docker-compose up -d
```

### 4. Test Agents

```bash
# Test job hunter
curl -X POST http://localhost:8000/api/v1/commands/run-agent \
  -H "Content-Type: application/json" \
  -d '{"agent": "job_hunter"}'

# Test email manager
curl -X POST http://localhost:8000/api/v1/commands/run-agent \
  -H "Content-Type: application/json" \
  -d '{"agent": "email_manager"}'

# Test personal assistant
curl -X POST http://localhost:8000/api/v1/commands/run-agent \
  -H "Content-Type: application/json" \
  -d '{"agent": "personal_assistant"}'
```

### 5. Monitor Costs

```bash
# Check cost summary
curl http://localhost:8000/api/v1/costs/summary

# Check usage history
curl http://localhost:8000/api/v1/costs/usage?days=7
```

---

## 📊 Monitoring

### Health Checks

```bash
# System health
GET /health

# OpenClaw health
GET /api/v1/integrations/openclaw/health

# Gmail health
GET /api/v1/integrations/gmail/health
```

### Logs

```bash
# View logs
docker-compose logs -f backend

# View specific agent logs
docker-compose logs -f backend | grep "JobHunterAgent"
docker-compose logs -f backend | grep "EmailManagerAgent"
```

### Metrics

```bash
# Job statistics
GET /api/v1/jobs/stats

# Contact statistics
GET /api/v1/contacts/stats

# Task statistics
GET /api/v1/tasks/stats/summary

# Email statistics
GET /api/v1/email-threads/stats/summary

# Cost summary
GET /api/v1/costs/summary
```

---

## 🐛 Troubleshooting

### OpenClaw Rate Limit Exceeded

```
Error: OpenClawRateLimitError
```

**Solution:** Wait for rate limit reset (24 hours) or upgrade OpenClaw plan.

### Gmail Authentication Failed

```
Error: Gmail API authentication failed
```

**Solution:** 
1. Verify `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`
2. Check token expiration
3. Re-authenticate if needed

### Cost Budget Exceeded

```
Error: OpenClawBudgetExceededError
```

**Solution:**
1. Check cost summary: `GET /api/v1/costs/summary`
2. Adjust budget in `.env`: `MAX_DAILY_AI_COST_USD`, `MAX_MONTHLY_AI_COST_USD`
3. Wait for budget reset (daily/monthly)

### Scheduled Tasks Not Running

**Solution:**
1. Check scheduler status in logs
2. Verify timezone: `Asia/Bangkok`
3. Restart backend: `docker-compose restart backend`

---

## 🎓 Best Practices

### Cost Optimization
1. Use caching (enabled by default)
2. Monitor daily costs
3. Set appropriate rate limits
4. Use fallback scrapers when possible

### Email Management
1. Process emails regularly (every 30 min)
2. Review urgent emails immediately
3. Complete action items promptly
4. Archive processed emails

### Job Discovery
1. Run 2x per day for best results
2. Review high-scoring jobs (>7.0) first
3. Apply to top opportunities quickly
4. Track application status

### Network Building
1. Discover contacts regularly
2. Personalize outreach messages
3. Log all interactions
4. Follow up consistently

---

## 📚 Additional Resources

- [Implementation Complete](./IMPLEMENTATION_COMPLETE.md) - Full implementation details
- [System Status](./SYSTEM_STATUS.md) - Current system status
- [Quick Start](./QUICK_START.md) - Getting started guide
- [API Documentation](http://localhost:8000/docs) - Interactive API docs

---

**Version:** 3.1.0  
**Last Updated:** 2024-01-15  
**Status:** Production Ready ✅

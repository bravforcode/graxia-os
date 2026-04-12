# Tasks: Personal AI Assistant Integration

## Overview
แผนงานสำหรับสร้าง Personal AI Assistant Integration ที่รวม OpenClaw + n8n + Obsidian เข้ากับระบบ BRAVOS ที่มีอยู่

**Timeline:** 8 สัปดาห์ (Phase 1 MVP)  
**Effort:** 20-30 ชั่วโมง/สัปดาห์  
**Budget:** <$80/เดือน

**Revised Timeline (realistic estimates):**
- Week 1-2: Foundation (Tasks 1-3) - 36-46 hours
- Week 3-4: Job Hunter + Scrapers (Tasks 4-5) - 44-54 hours
- Week 5: Network Builder + Email Manager start (Tasks 6-7) - 20-30 hours
- Week 6: Email Manager complete + Personal Assistant (Tasks 7-8) - 24-30 hours
- Week 7: Approval Flow + Infrastructure start (Tasks 9-12) - 24-30 hours
- Week 8: Infrastructure complete (Tasks 13-15) - 28-36 hours

**Total Effort:** 176-226 hours over 8 weeks (22-28 hours/week average)

## Phase 1: Foundation (Week 1-2)

### Pre-Development Checklist

**ต้องทำให้เสร็จก่อนเริ่ม Week 1 - ป้องกันปัญหาวันแรก**

#### Accounts and Access
- [ ] OpenClaw account created and API key obtained
- [ ] OpenClaw pricing confirmed (cost per request, monthly limits)
- [ ] Gmail OAuth app created in Google Cloud Console
- [ ] Telegram bot created (@BotFather), token obtained
- [ ] Supabase/Railway project created, DATABASE_URL obtained
- [ ] Upstash Redis instance created, REDIS_URL obtained
- [ ] Gemini API key obtained, pricing confirmed

#### Existing BRAVOS System Verified
- [ ] Can run BRAVOS locally without errors
- [ ] Existing tests pass (100%)
- [ ] Existing database migrations run cleanly
- [ ] Existing EventBus works (test event publish/subscribe)
- [ ] Existing Telegram bot responds to /start

#### Development Environment
- [ ] Python version confirmed (3.11+)
- [ ] Virtual environment set up
- [ ] All existing dependencies install cleanly
- [ ] Pre-commit hooks configured (ruff, mypy)
- [ ] GitHub Actions pipeline exists for CI/CD

#### Cost Safeguards Before Any API Calls
- [ ] OpenClaw monthly budget limit set in account dashboard
- [ ] Gemini billing alert set at $10/month
- [ ] Hard-coded cost limits in code verified
- [ ] Telegram alert for cost >80% budget tested

---

### Task 1: ขยาย Database Schema
**Priority:** MUST HAVE  
**Estimated Time:** 12-16 hours  
**Dependencies:** None

สร้าง tables ใหม่ 8 tables สำหรับ Phase 1 MVP

**Sub-tasks:**
- [ ] 1.1 สร้าง migration file สำหรับ 8 tables ใหม่
  - `job_postings` - งานที่พบจาก scrapers
  - `email_threads` - เก็บ email conversations
  - `email_messages` - เก็บ email แต่ละฉบับ
  - `assistant_tasks` - เก็บ tasks และ reminders
  - `network_interactions` - เก็บ interactions กับ contacts
  - `openclaw_usage` - track OpenClaw API costs
  - `scraper_runs` - track scraper execution history
  - `api_rate_limits` - rate limiting per service
- [ ] 1.2 เพิ่ม indexes สำหรับ performance
  - Index บน `job_postings.source_hash` (UNIQUE)
  - Index บน `job_postings.fit_score DESC`
  - Index บน `email_threads.priority DESC`
  - Index บน `assistant_tasks.status, priority DESC`
  - Index บน `network_interactions.contact_id, interaction_at DESC`
  - Index บน `openclaw_usage.created_at DESC`
- [ ] 1.3 เพิ่ม foreign keys และ constraints
- [ ] 1.4 เขียน unit tests สำหรับ models
- [ ] 1.5 Run migration และ verify schema

**Acceptance Criteria:**
- ✓ Migration runs successfully โดยไม่มี errors
- ✓ ทุก table มี indexes ที่จำเป็น
- ✓ Foreign keys ทำงานถูกต้อง
- ✓ Unit tests pass 100%
- ✓ Query performance: SELECT < 50ms, INSERT < 100ms

**References:** Requirement 10 (Database Schema)

---

### Task 2: ขยาย EventBus
**Priority:** MUST HAVE  
**Estimated Time:** 8-10 hours  
**Dependencies:** None

เพิ่ม event types ใหม่ 5 types สำหรับ agents ใหม่

**Sub-tasks:**
- [ ] 2.1 เพิ่ม event types ใหม่
  - `job.found` - เมื่อพบงานใหม่
  - `contact.discovered` - เมื่อพบ contact ใหม่
  - `email.received` - เมื่อได้รับ email ใหม่
  - `task.created` - เมื่อสร้าง task ใหม่
  - `approval.requested` - เมื่อต้องการ approval
- [ ] 2.2 เพิ่ม event handlers สำหรับแต่ละ type
- [ ] 2.3 เพิ่ม event validation และ schema
- [ ] 2.4 เขียน integration tests สำหรับ event flow
- [ ] 2.5 เพิ่ม event logging และ monitoring

**Acceptance Criteria:**
- ✓ Event publishing < 10ms
- ✓ Event processing < 100ms (P95)
- ✓ Event delivery guarantee: at-least-once
- ✓ Failed events retry 3 times with exponential backoff
- ✓ Integration tests pass 100%

**References:** Requirement 9 (EventBus Extensions)

---

### Task 3: สร้าง OpenClaw Integration Module
**Priority:** MUST HAVE  
**Estimated Time:** 16-20 hours  
**Dependencies:** Task 1 (scraper_cache table)

สร้าง module สำหรับเชื่อมต่อกับ OpenClaw API

**Sub-tasks:**
- [ ] 3.1 สร้าง `OpenClawClient` class
  - API authentication
  - Request/response handling
  - Error handling และ retry logic
- [ ] 3.2 สร้าง caching layer
  - Cache scraping results ใน Redis (4 hours TTL)
  - Fallback to database cache
  - Cache invalidation strategy
- [ ] 3.3 สร้าง rate limiting
  - Max 50 requests/day สำหรับ LinkedIn
  - Max 20 requests/day สำหรับ Network Builder
  - Alert เมื่อใกล้ถึง limit
- [ ] 3.4 สร้าง cost tracking
  - Track API usage ใน `openclaw_usage` table
  - Calculate daily/monthly costs
  - Alert เมื่อเกิน budget ($50/month)
- [ ] 3.5 สร้าง fallback mechanism
  - Tier 1: Direct scraper
  - Tier 2: OpenClaw
  - Tier 3: Cached data
  - Tier 4: Alert user
- [ ] 3.6 เขียน unit tests และ integration tests
- [ ] 3.7 เขียน documentation

**Acceptance Criteria:**
- ✓ API calls succeed >95% of the time
- ✓ Cache hit rate >40%
- ✓ Cost tracking accurate within $1
- ✓ Fallback works automatically
- ✓ Rate limiting prevents overage
- ✓ Tests pass 100%
- ✓ Documentation complete

**References:** Requirement 3 (OpenClaw Integration), ADR-001

---

## Phase 2: Core Agents (Week 3-6)

### Task 4: สร้าง Job Hunter Agent
**Priority:** MUST HAVE  
**Estimated Time:** 20-24 hours  
**Dependencies:** Task 1, Task 2, Task 3

สร้าง agent ที่หางานอัตโนมัติจาก 5-7 platforms

**Sub-tasks:**
- [ ] 4.1 สร้าง `JobHunterAgent` class
  - Inherit from `BaseAgent`
  - Implement `execute()` method
  - Handle events: `scraper.completed`, `schedule.daily`
- [ ] 4.2 สร้าง job scoring logic
  - Calculate `fit_score` (0-10) based on skills
  - Calculate `value_score` (0-10) based on budget/salary
  - Calculate `urgency_score` (0-10) based on deadline
- [ ] 4.3 สร้าง deduplication logic
  - Use source hash (SHA256 of source + source_id)
  - Check existing opportunities
  - Update if changed
- [ ] 4.4 สร้าง notification logic
  - Send to Telegram if score >7
  - Daily summary if score 5-7
  - Skip if score <5
- [ ] 4.5 เขียน unit tests
- [ ] 4.6 เขียน integration tests
- [ ] 4.7 เขียน property-based tests (Hypothesis)
  - Property: Deduplication is idempotent
  - Property: Scoring is deterministic
  - Property: All jobs are stored

**Acceptance Criteria:**
- ✓ Find 50+ jobs per week
- ✓ Deduplication accuracy >99%
- ✓ Scoring accuracy >80% (manual validation)
- ✓ Notification latency <5 minutes
- ✓ Tests pass 100%
- ✓ Property tests pass 1000+ examples

**References:** Requirement 1 (Job Hunter), Requirement 4 (Scoring)

---

### Task 5: สร้าง Enhanced Scrapers
**Priority:** MUST HAVE  
**Estimated Time:** 24-30 hours  
**Dependencies:** Task 3 (OpenClaw)

สร้าง scrapers สำหรับ 5-7 platforms

**Sub-tasks:**
- [ ] 5.1 สร้าง `LinkedInScraper`
  - Use OpenClaw for authentication
  - Search jobs by keywords
  - Parse job details
  - Handle pagination (max 50 pages/day)
- [ ] 5.2 สร้าง `UpworkScraper`
  - Use OpenClaw for authentication
  - Search jobs by category
  - Parse job details
  - Handle rate limiting
- [ ] 5.3 สร้าง `FiverrScraper`
  - Direct HTTP scraping (no auth needed)
  - Search gigs by keywords
  - Parse gig details
- [ ] 5.4 สร้าง `FastWorkScraper`
  - Direct HTTP scraping
  - Search jobs by category
  - Parse job details (Thai language)
- [ ] 5.5 สร้าง `DevpostScraper`
  - Direct HTTP scraping
  - Search hackathons
  - Parse event details
- [ ] 5.6 สร้าง `RSSReaderScraper`
  - Read RSS feeds
  - Parse articles
  - Extract job postings
- [ ] 5.7 เขียน tests สำหรับแต่ละ scraper
- [ ] 5.8 เขียน integration tests

**Acceptance Criteria (Platform-Specific):**
- ✓ LinkedIn: 5-15 job postings per run
- ✓ Upwork: 10-20 job postings per run
- ✓ FastWork: 10-20 job postings per run
- ✓ Fiverr: 5-10 relevant gigs per run
- ✓ Devpost: 1-5 hackathons per run
- ✓ RSS: 0-20 jobs per run (varies by feed activity)
- ✓ Parsing accuracy >90%
- ✓ Error rate <5%
- ✓ Respect rate limits
- ✓ Tests pass 100%

**References:** Requirement 2 (Enhanced Scrapers)

---

### Task 6: สร้าง Network Builder Agent
**Priority:** MUST HAVE  
**Estimated Time:** 16-20 hours  
**Dependencies:** Task 1, Task 2, Task 3

สร้าง agent ที่หาและจัดการ contacts อัตโนมัติ

**Sub-tasks:**
- [ ] 6.1 สร้าง `NetworkBuilderAgent` class
  - Search LinkedIn for relevant contacts
  - Calculate `value_score` (0-10)
  - Calculate `relationship_strength` (0.0-1.0)
- [ ] 6.2 สร้าง contact scoring logic
  - Based on: title, company, mutual connections
  - Identify bridge nodes
  - Identify network clusters
- [ ] 6.3 สร้าง outreach logic
  - Generate personalized messages
  - Request approval before sending
  - Track responses
- [ ] 6.4 สร้าง relationship tracking
  - Track interactions
  - Update relationship strength
  - Suggest follow-ups
- [ ] 6.5 เขียน tests

**Acceptance Criteria:**
- ✓ Find 10+ quality contacts per month
- ✓ Scoring accuracy >75%
- ✓ Outreach message quality score ≥4/5 (manual review of 10 samples) - Week 6-8
- ✓ Response rate ≥20% of approved outreach - End of Month 2 (long-term metric)
- ✓ Tests pass 100%

**References:** Requirement 5 (Network Builder)

---

### Task 7: สร้าง Email Manager Agent
**Priority:** MUST HAVE  
**Estimated Time:** 20-24 hours  
**Dependencies:** Task 1, Task 2

สร้าง agent ที่จัดการ email อัตโนมัติ

**Sub-tasks:**
- [ ] 7.1 สร้าง `EmailManagerAgent` class
  - Connect to Gmail API
  - Fetch new emails
  - Parse email content
- [ ] 7.2 สร้าง email classification
  - Categories: job, networking, spam, personal, other
  - Use Gemini for classification
  - Confidence threshold >0.8
- [ ] 7.3 สร้าง email threading
  - Group emails by conversation
  - Track thread status
  - Identify action items
- [ ] 7.4 สร้าง auto-reply logic
  - Generate replies using Gemini
  - Request approval before sending
  - Track sent replies
- [ ] 7.5 สร้าง action extraction
  - Extract dates, amounts, names (NER)
  - Create tasks automatically
  - Set reminders
- [ ] 7.6 เขียน tests

**Acceptance Criteria:**
- ✓ Classification accuracy >85%
- ✓ Threading accuracy >90%
- ✓ Action extraction accuracy >80%
- ✓ Response time <2 hours (automated)
- ✓ Tests pass 100%

**References:** Requirement 6 (Email Manager)

---

## Phase 3: Assistant & Approval (Week 6-7)

### Task 8: สร้าง Personal Assistant Agent
**Priority:** MUST HAVE  
**Estimated Time:** 24-30 hours  
**Dependencies:** Task 1, Task 2, Task 7

สร้าง agent ที่ทำหน้าที่เป็นเลขาส่วนตัว

**Sub-tasks:**
- [ ] 8.1 สร้าง `PersonalAssistantAgent` class
  - Coordinate all other agents
  - Handle Telegram commands
  - Manage notifications
- [ ] 8.2 สร้าง daily briefing
  - Summary of new jobs (top 10)
  - Summary of new contacts (top 5)
  - Summary of emails (action items)
  - Summary of tasks (due today)
  - Send at 8:00 AM daily
- [ ] 8.3 สร้าง task management
  - Create tasks from emails
  - Set reminders
  - Track completion
  - Send notifications
- [ ] 8.4 สร้าง notification rate limiting
  - Urgent alerts (priority ≥9): Always delivered immediately, bypass limit
  - High priority (priority 7-8): Queue and deliver when limit resets
  - Normal (priority 1-6): Batch into hourly digest
  - Max 10 messages/hour for non-urgent
  - Max queue size: 50 messages (oldest dropped if exceeded)
- [ ] 8.5 สร้าง cost monitoring
  - Track OpenClaw costs
  - Track Gemini costs
  - Alert if >$50/month
  - Suggest optimizations
- [ ] 8.6 สร้าง Telegram command handlers
  - `/status` - system status
  - `/jobs` - recent jobs
  - `/contacts` - recent contacts
  - `/tasks` - pending tasks
  - `/costs` - API costs
- [ ] 8.7 เขียน tests

**Acceptance Criteria:**
- ✓ Daily briefing sent on time >99%
- ✓ Notification latency <5 minutes
- ✓ Rate limiting works correctly
- ✓ Cost tracking accurate within $1
- ✓ Telegram commands respond <5 seconds
- ✓ Tests pass 100%

**References:** Requirement 7 (Personal Assistant)

---

### Task 9: สร้าง Approval Flow System
**Priority:** MUST HAVE  
**Estimated Time:** 12-16 hours  
**Dependencies:** Task 8

สร้างระบบอนุมัติก่อนดำเนินการอัตโนมัติ

**Sub-tasks:**
- [ ] 9.1 สร้าง `ApprovalFlowManager` class
  - Create approval requests
  - Send to Telegram with inline keyboard
  - Handle approve/reject responses
  - Execute approved actions
- [ ] 9.2 สร้าง approval types
  - Email sending
  - LinkedIn outreach
  - Job application
  - High-cost actions (>$10)
- [ ] 9.3 สร้าง timeout logic
  - Auto-reject after 24 hours
  - Send reminder after 12 hours
  - Escalate urgent items
- [ ] 9.4 สร้าง audit trail
  - Log all approval requests
  - Log all decisions
  - Track response time
- [ ] 9.5 เขียน tests

**Acceptance Criteria:**
- ✓ Approval requests sent <1 minute
- ✓ User responses processed <10 seconds
- ✓ Timeout works correctly
- ✓ Audit trail complete
- ✓ Tests pass 100%

**References:** Requirement 8 (Approval Flow)

---

## Phase 4: Infrastructure (Week 7-8)

### Task 10: Configuration Management
**Priority:** MUST HAVE  
**Estimated Time:** 8-10 hours  
**Dependencies:** All agents

สร้างระบบจัดการ configuration

**Sub-tasks:**
- [ ] 10.1 สร้าง configuration schema
  - Agent settings
  - API keys
  - Rate limits
  - Notification preferences
- [ ] 10.2 สร้าง validation
  - Validate on startup
  - Validate on update
  - Provide helpful error messages
- [ ] 10.3 สร้าง hot reload
  - File watcher for config changes
  - Graceful reload within 5 minutes
  - No downtime
- [ ] 10.4 สร้าง configuration UI
  - API endpoints for CRUD
  - Frontend forms
  - Validation feedback
- [ ] 10.5 เขียน tests

**Acceptance Criteria:**
- ✓ Configuration loads <1 second
- ✓ Validation catches all errors
- ✓ Hot reload works without downtime
- ✓ UI is user-friendly
- ✓ Tests pass 100%

**References:** Requirement 11 (Configuration)

---

### Task 11: Monitoring & Metrics
**Priority:** MUST HAVE  
**Estimated Time:** 12-16 hours  
**Dependencies:** All agents

สร้างระบบ monitoring และ metrics

**Sub-tasks:**
- [ ] 11.1 สร้าง metrics collection
  - Agent execution time
  - API response time
  - Error rates
  - Cost tracking
  - Cache hit rates
- [ ] 11.2 สร้าง health checks
  - Database connectivity
  - Redis connectivity
  - External API availability
  - Agent status
- [ ] 11.3 สร้าง alerting
  - Error rate >5%
  - Response time >1 second
  - Cost >$50/month
  - Downtime >5 minutes
- [ ] 11.4 สร้าง dashboard
  - Real-time metrics
  - Historical trends
  - Cost breakdown
  - Agent performance
- [ ] 11.5 เขียน tests

**Acceptance Criteria:**
- ✓ Metrics collected every 1 minute
- ✓ Health checks run every 5 minutes
- ✓ Alerts sent <1 minute
- ✓ Dashboard loads <2 seconds
- ✓ Tests pass 100%

**References:** Requirement 12 (Monitoring)

---

### Task 12: Error Handling & Retry
**Priority:** MUST HAVE  
**Estimated Time:** 10-12 hours  
**Dependencies:** All agents

สร้างระบบ error handling และ retry

**Sub-tasks:**
- [ ] 12.1 สร้าง retry mechanism
  - Exponential backoff (1s, 2s, 4s, 8s)
  - Max 3 retries
  - Idempotent operations
- [ ] 12.2 สร้าง circuit breaker
  - Open after 3 consecutive failures
  - Half-open after 5 minutes
  - Close after 1 success
- [ ] 12.3 สร้าง error logging
  - Log all errors with context
  - Track error patterns
  - Alert on new error types
- [ ] 12.4 สร้าง graceful degradation
  - Fallback to cached data
  - Disable non-critical features
  - Maintain core functionality
- [ ] 12.5 เขียน tests

**Acceptance Criteria:**
- ✓ Retry works correctly
- ✓ Circuit breaker prevents cascade failures
- ✓ Error logs are complete
- ✓ Graceful degradation works
- ✓ Tests pass 100%

**References:** Requirement 13 (Error Handling)

---

### Task 13: Security Implementation
**Priority:** MUST HAVE  
**Estimated Time:** 12-16 hours  
**Dependencies:** All components

สร้างระบบ security

**Sub-tasks:**
- [ ] 13.1 สร้าง encryption
  - Encrypt API keys (AES-256)
  - Encrypt PII in database
  - Secure key storage
- [ ] 13.2 สร้าง authentication
  - JWT tokens
  - Token refresh
  - Session management
- [ ] 13.3 สร้าง authorization
  - Role-based access control
  - Agent permissions
  - API endpoint protection
- [ ] 13.4 สร้าง rate limiting
  - Per-user limits
  - Per-endpoint limits
  - DDoS protection
- [ ] 13.5 สร้าง audit logging
  - Log all sensitive operations
  - Track data access
  - Compliance reporting
- [ ] 13.6 Run security scan (OWASP Top 10)
- [ ] 13.7 เขียน tests

**Acceptance Criteria:**
- ✓ All API keys encrypted
- ✓ All PII encrypted
- ✓ Authentication works correctly
- ✓ Authorization prevents unauthorized access
- ✓ Rate limiting works
- ✓ Security scan passes
- ✓ Tests pass 100%

**References:** Requirement 14 (Security)

---

### Task 14: API Endpoints
**Priority:** MUST HAVE  
**Estimated Time:** 16-20 hours  
**Dependencies:** All agents

สร้าง API endpoints สำหรับ frontend

**Sub-tasks:**
- [ ] 14.1 สร้าง job endpoints
  - `GET /api/v1/jobs` - list jobs
  - `GET /api/v1/jobs/{id}` - job details
  - `POST /api/v1/jobs/{id}/apply` - apply to job
- [ ] 14.2 สร้าง contact endpoints
  - `GET /api/v1/contacts` - list contacts
  - `GET /api/v1/contacts/{id}` - contact details
  - `POST /api/v1/contacts/{id}/outreach` - send outreach
- [ ] 14.3 สร้าง email endpoints
  - `GET /api/v1/emails` - list emails
  - `GET /api/v1/emails/{id}` - email details
  - `POST /api/v1/emails/{id}/reply` - reply to email
- [ ] 14.4 สร้าง task endpoints
  - `GET /api/v1/tasks` - list tasks
  - `POST /api/v1/tasks` - create task
  - `PUT /api/v1/tasks/{id}` - update task
  - `DELETE /api/v1/tasks/{id}` - delete task
- [ ] 14.5 สร้าง metrics endpoints
  - `GET /api/v1/metrics` - system metrics
  - `GET /api/v1/costs` - cost breakdown
- [ ] 14.6 สร้าง config endpoints
  - `GET /api/v1/config` - get config
  - `PUT /api/v1/config` - update config
- [ ] 14.7 เขียน API documentation (OpenAPI)
- [ ] 14.8 เขียน tests

**Acceptance Criteria:**
- ✓ All endpoints respond <200ms (P95)
- ✓ All endpoints have proper error handling
- ✓ All endpoints have authentication
- ✓ API documentation complete
- ✓ Tests pass 100%

**References:** Requirement 15 (API Endpoints)

---

### Task 15: Testing & Documentation
**Priority:** MUST HAVE  
**Estimated Time:** 16-20 hours  
**Dependencies:** All tasks

สร้าง comprehensive testing และ documentation

**Sub-tasks:**
- [ ] 15.1 เขียน integration tests
  - End-to-end workflows
  - Agent interactions
  - External API integrations
- [ ] 15.2 เขียน property-based tests
  - Deduplication properties
  - Scoring properties
  - Caching properties
- [ ] 15.3 เขียน load tests
  - 100 concurrent agent executions
  - 1000 requests/minute
  - Database performance
- [ ] 15.4 เขียน regression tests
  - Test all bug fixes
  - Prevent regressions
- [ ] 15.5 เขียน user documentation
  - Setup guide
  - Configuration guide
  - Troubleshooting guide
  - API documentation
- [ ] 15.6 เขียน developer documentation
  - Architecture overview
  - Code structure
  - Contributing guide
- [ ] 15.7 สร้าง operational runbook
  - Common scenarios
  - Diagnosis steps
  - Solutions
- [ ] 15.8 Achieve >80% test coverage

**Acceptance Criteria:**
- ✓ All integration tests pass
- ✓ All property tests pass 1000+ examples
- ✓ Load tests pass without errors
- ✓ Test coverage >80%
- ✓ Documentation complete
- ✓ Runbook covers 7+ scenarios

**References:** Requirement 16 (Testing)

---

## Rollback Plan

### Go/No-Go Criteria (End of Week 8)

**GO Criteria (proceed to Phase 2):**
- ✓ All MUST HAVE tasks completed
- ✓ All tests passing
- ✓ System uptime >95% for 1 week
- ✓ Cost <$60/month
- ✓ 30+ jobs found in test week
- ✓ 5+ contacts found in test week (not month)
- ✓ No critical bugs

**NO-GO Criteria (rollback or extend Phase 1):**
- ✗ >3 critical bugs
- ✗ System uptime <90%
- ✗ Cost >$80/month
- ✗ <20 jobs found in test week
- ✗ <3 contacts found in test week
- ✗ Test coverage <70%

### Rollback Procedure

1. **Stop all agents** - Disable Celery tasks
2. **Backup database** - Full PostgreSQL dump
3. **Revert migrations** - Alembic downgrade
4. **Restore old code** - Git revert
5. **Verify old system** - Run health checks
6. **Notify user** - Telegram alert

### Extend Phase 1 Procedure

1. **Identify blockers** - List incomplete tasks
2. **Re-estimate effort** - Update timeline
3. **Prioritize fixes** - Focus on critical issues
4. **Set new deadline** - Add 1-2 weeks
5. **Continue development** - Resume work

---

## Definition of Done

แต่ละ task ถือว่า "เสร็จสมบูรณ์" เมื่อ:

- ✓ Code เขียนเสร็จและ commit แล้ว
- ✓ Unit tests pass (>80% coverage สำหรับ module นั้น)
- ✓ Integration tests pass
- ✓ Property-based tests pass (ถ้ามี)
- ✓ Error handling ครอบคลุมทุก failure modes
- ✓ Metrics emitted to monitoring system
- ✓ Telegram notification on critical failure works
- ✓ Code reviewed (self-review สำหรับ solo dev)
- ✓ Documentation updated
- ✓ No critical bugs
- ✓ Performance meets SLA

---

## Risk Register

| Risk | Probability | Impact | Mitigation | Owner |
|------|------------|--------|-----------|-------|
| LinkedIn blocks scraping | High | High | Use official API + PhantomBuster fallback | Task 5 |
| OpenAI API cost explosion | Medium | High | Budget caps + fallback to Gemini | Task 3 |
| Solo developer burnout | High | Critical | Scope to MVP first, take breaks | All |
| Regulatory issues (GDPR) | Medium | High | Legal review before building | Task 13 |
| OpenClaw API downtime | Medium | Medium | 3-tier fallback system | Task 3 |
| Database performance issues | Low | High | Proper indexing + query optimization | Task 1 |
| Telegram rate limiting | Low | Medium | Notification batching + rate limiting | Task 8 |
| Gmail API quota exceeded | Low | Medium | Reduce polling frequency | Task 7 |

---

## Dependency Graph

```
Task 1 (Database) ─┬─→ Task 3 (OpenClaw) ─→ Task 4 (Job Hunter)
                   │                        └─→ Task 5 (Scrapers)
                   │                        └─→ Task 6 (Network Builder)
                   │
                   ├─→ Task 7 (Email Manager) ─→ Task 8 (Personal Assistant) ─→ Task 9 (Approval)
                   │
                   └─→ Task 2 (EventBus) ─────→ All Agents

Task 10-15 (Infrastructure) ─→ Depends on all agents
```

---

## Progress Tracking

**Week 1-2:** Tasks 1-3 (Foundation)  
**Week 3-4:** Tasks 4-5 (Job Hunter + Scrapers)  
**Week 5:** Tasks 6-7 start (Network Builder + Email Manager)  
**Week 6:** Tasks 7-8 (Email Manager complete + Personal Assistant)  
**Week 7:** Tasks 9-12 (Approval + Infrastructure)  
**Week 8:** Tasks 13-15 (Security + API + Testing)

**Current Status:** Not started  
**Completed Tasks:** 0/15  
**Estimated Completion:** Week 8

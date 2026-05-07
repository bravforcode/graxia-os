# 📋 PHASE 2 PREPARATION CHECKLIST

**Phase:** Phase 2 (High Priority Fixes)  
**Duration:** Sprint 1 (2 weeks)  
**Total Tasks:** 5 tasks  
**Estimated Effort:** 12 hours  
**Target Start:** After Phase 1 deployment  

---

## 🎯 PHASE 2 OVERVIEW

Phase 2 addresses **3 HIGH priority** and **2 MEDIUM priority** security and architecture issues that could lead to data loss, system compromise, or performance degradation.

### Issues to Address

| ID | Priority | Issue | Effort | Owner |
|----|----------|-------|--------|-------|
| [H-01] | 🔴 HIGH | Enforce Required Secrets Validation at Startup | 1.5h | Backend Dev |
| [H-02] | 🔴 HIGH | Implement Graceful Shutdown for Event Bus | 2.5h | Senior Backend |
| [H-03] | 🔴 HIGH | Add Database Indexes for Common Query Patterns | 3h | Backend + DBA |
| [M-02] | 🟠 MEDIUM | Implement Event Bus Queue Size Limit | 1.5h | Backend Dev |
| [M-04] | 🟠 MEDIUM | Add CSRF Token Expiry Timestamp | 2h | Backend Dev |

**Total Effort:** 10.5 hours (12h with buffer)

---

## 📚 PHASE 2 TASKS SUMMARY

### TASK 2.1: Enforce Required Secrets Validation at Startup [H-01]

**Priority:** 🔴 HIGH  
**Effort:** 1.5 hours  
**Owner:** Backend Developer

**Problem:**
- Default values for `SECRET_KEY`, `ENCRYPTION_KEY`, `POSTGRES_PASSWORD` are weak placeholders
- If developers forget to change them, system has critical vulnerabilities
- Could lead to JWT token forgery, data decryption, database compromise

**Solution:**
- Change defaults from placeholders to `None`
- Add `@model_validator` to check required secrets at startup
- Raise `RuntimeError` if secrets are missing or look like placeholders
- Allow testing mode to use defaults

**Files to Modify:**
- `backend/app/config.py` — Add validation logic
- `.env.example` — Update with clear instructions
- `backend/tests/test_config_validation.py` — Create test suite

**Acceptance Criteria:**
- ✅ Application doesn't start if required secrets not configured (except testing mode)
- ✅ Error message clearly states which secrets are missing
- ✅ Testing mode can still use default values
- ✅ Production validation checks secret strength (length, entropy)

**Breaking Changes:**
- Developers must set `SECRET_KEY`, `ENCRYPTION_KEY`, `POSTGRES_PASSWORD` in `.env`
- CI/CD pipelines must update environment variables

---

### TASK 2.2: Implement Graceful Shutdown for Event Bus [H-02]

**Priority:** 🔴 HIGH  
**Effort:** 2.5 hours  
**Owner:** Senior Backend Developer

**Problem:**
- When `stop()` is called, event bus stops immediately
- Events in queue are not processed
- Running handlers are not waited for completion
- Could cause data loss or inconsistent state

**Solution:**
- Track processing tasks in `_processing_tasks` set
- Create `_process_event()` method separate from main loop
- Update `start_processing()` to wait for tasks to complete before shutdown
- Add configurable shutdown timeout (default 30s)

**Files to Modify:**
- `backend/app/core/event_bus.py` — Add graceful shutdown logic
- `backend/tests/test_event_bus_shutdown.py` — Create test suite

**Acceptance Criteria:**
- ✅ Events in queue are processed before shutdown
- ✅ Running handlers are waited for completion (with timeout)
- ✅ Shutdown timeout configurable via environment variable
- ✅ Logs show number of pending tasks during shutdown
- ✅ Test verifies graceful shutdown behavior

**Performance Impact:**
- Shutdown time increases by max 30s (configurable)
- No impact on runtime performance

---

### TASK 2.3: Add Database Indexes for Common Query Patterns [H-03]

**Priority:** 🔴 HIGH  
**Effort:** 3 hours  
**Owner:** Backend Developer + DBA

**Problem:**
- No indexes for common query patterns
- Full table scans on filtered queries
- Slow performance as data grows
- High database CPU usage

**Solution:**
- Analyze query patterns from logs and slow query logs
- Create Alembic migration to add indexes
- Add indexes for:
  - `opportunities`: status, score, created_at, (user_id, status)
  - `contacts`: email, organization
  - `email_threads`: (user_id, status), last_message_at
  - `assistant_tasks`: (user_id, status), priority
- Test migration on staging with production-like data

**Files to Create:**
- `backend/alembic/versions/XXX_add_performance_indexes.py` — Migration
- `backend/scripts/benchmark_queries.py` — Benchmark script

**Acceptance Criteria:**
- ✅ Migration runs on production without long table locks (< 5 min)
- ✅ Query performance improves >50% for filtered list operations
- ✅ Database size increases < 10%
- ✅ Rollback migration works correctly

**Production Deployment:**
```bash
# Run during low-traffic window
alembic upgrade head

# Monitor query performance
python scripts/benchmark_queries.py --compare-before-after

# Rollback if issues
alembic downgrade -1
```

---

### TASK 2.4: Implement Event Bus Queue Size Limit [M-02]

**Priority:** 🟠 MEDIUM (elevated to Phase 2 due to memory risk)  
**Effort:** 1.5 hours  
**Owner:** Backend Developer  
**Dependencies:** TASK 2.2 (Graceful Shutdown)

**Problem:**
- `asyncio.Queue()` has no `maxsize` limit
- Could cause memory exhaustion if events emitted faster than processed
- No backpressure mechanism

**Solution:**
- Set `maxsize=10000` on queue
- Implement backpressure mechanism when queue full
- Add metrics for queue depth
- Add alert rule for queue depth > 80%

**Files to Modify:**
- `backend/app/core/event_bus.py` — Add queue size limit
- `backend/tests/test_event_bus_backpressure.py` — Create test suite

**Acceptance Criteria:**
- ✅ Queue size limited to 10,000 events (configurable)
- ✅ When queue full, `emit()` blocks or raises exception (configurable)
- ✅ Metrics show queue depth, emit rate, process rate
- ✅ Alert triggers when queue depth high

---

### TASK 2.5: Add CSRF Token Expiry Timestamp [M-04]

**Priority:** 🟠 MEDIUM (elevated to Phase 2 due to security impact)  
**Effort:** 2 hours  
**Owner:** Backend Developer  
**Dependencies:** TASK 1.1 (CSRF Timing Fix)

**Problem:**
- CSRF tokens don't have expiry timestamp
- Leaked tokens can be used indefinitely until session expires
- Increases attack window

**Solution:**
- Add timestamp (Unix epoch) to token payload
- Update `validate_csrf_token_signature()` to check expiry
- Add `CSRF_TOKEN_EXPIRY_HOURS` config (default 1 hour)
- Backward compatible with tokens without timestamp (grace period 1 week)

**Files to Modify:**
- `backend/app/middleware/security.py` — Add expiry logic
- `backend/tests/test_csrf_expiry.py` — Create test suite

**Acceptance Criteria:**
- ✅ CSRF tokens have expiry timestamp
- ✅ Expired tokens rejected with clear error message
- ✅ Token expiry configurable via environment variable
- ✅ Backward compatible with old tokens (grace period 1 week)

---

## 🚀 PHASE 2 PREPARATION STEPS

### 1. Review Phase 1 Deployment

**Before starting Phase 2:**
- [ ] Phase 1 deployed to production
- [ ] Phase 1 verification scripts passing in production
- [ ] No production incidents related to Phase 1 changes
- [ ] Monitoring shows expected behavior

### 2. Team Assignment

**Assign owners to Phase 2 tasks:**
- [ ] TASK 2.1: Backend Developer assigned
- [ ] TASK 2.2: Senior Backend Developer assigned
- [ ] TASK 2.3: Backend Developer + DBA assigned
- [ ] TASK 2.4: Backend Developer assigned
- [ ] TASK 2.5: Backend Developer assigned

### 3. Environment Setup

**Prepare development environment:**
- [ ] Staging database with production-like data volume
- [ ] Database backup and restore procedures tested
- [ ] Performance benchmarking tools installed
- [ ] Alembic migrations tested on staging

### 4. Documentation Review

**Review relevant documentation:**
- [ ] Implementation plan: `docs/plans/2026-05-07-graxia-implementation-plan.md`
- [ ] Audit report: `docs/audits/2026-05-07-graxia-ultra-audit.md`
- [ ] Phase 1 completion report: `docs/phase-reports/PHASE_1_COMPLETION_REPORT.md`

### 5. Sprint Planning

**Schedule Phase 2 sprint:**
- [ ] Sprint planning meeting scheduled
- [ ] Task breakdown reviewed with team
- [ ] Dependencies identified and documented
- [ ] Risks assessed and mitigation plans created

---

## 📊 PHASE 2 SUCCESS METRICS

### Security Metrics
- ✅ Zero high-priority security vulnerabilities
- ✅ All required secrets validated at startup
- ✅ CSRF tokens have expiry timestamps

### Performance Metrics
- ✅ List/filter queries < 50ms p95
- ✅ Event bus queue depth < 1000 under normal load
- ✅ Graceful shutdown completes within 30s

### Code Quality Metrics
- ✅ All configuration externalized
- ✅ 100% of critical paths have tests
- ✅ Database indexes optimized for common queries

---

## ⚠️ RISKS & MITIGATION

### Risk 1: Database Migration Locks Production

**Impact:** Service downtime during index creation  
**Probability:** Medium  
**Mitigation:**
- Use `CONCURRENTLY` option for index creation
- Run during low-traffic window
- Test on staging with production-like data volume
- Have rollback plan ready

**Contingency:**
- Rollback migration immediately if issues
- Create indexes in smaller batches
- Use online schema change tools if needed

### Risk 2: Breaking Changes in Secret Validation

**Impact:** Developers unable to start application locally  
**Probability:** High  
**Mitigation:**
- Clear communication to team
- Update documentation with migration guide
- Provide example `.env` file with all required secrets
- Add grace period with warnings before enforcing

**Contingency:**
- Temporary grace period with warnings instead of errors
- Provide script to generate secure secrets
- Update CI/CD pipelines first

### Risk 3: Event Bus Graceful Shutdown Timeout

**Impact:** Deployment takes longer than expected  
**Probability:** Low  
**Mitigation:**
- Make timeout configurable
- Test with realistic event volumes
- Monitor queue depth before deployment
- Drain queue before shutdown if possible

**Contingency:**
- Increase timeout if needed
- Force shutdown after extended timeout
- Log unprocessed events for manual recovery

---

## 📋 TASK 2.1 DETAILED CHECKLIST

Since TASK 2.1 is the first task of Phase 2, here's a detailed checklist:

### Pre-Implementation

- [ ] Read audit report section for [H-01]
- [ ] Read implementation plan section for TASK 2.1
- [ ] Review current `backend/app/config.py` implementation
- [ ] Identify all required secrets
- [ ] Document current default values

### Implementation

- [ ] Change default values from placeholders to `None`
- [ ] Add `@model_validator` method `validate_required_secrets()`
- [ ] Implement placeholder detection logic
- [ ] Add secret strength validation (length, entropy)
- [ ] Update `.env.example` with clear instructions
- [ ] Add testing mode exception

### Testing

- [ ] Create `backend/tests/test_config_validation.py`
- [ ] Test startup without secrets (should fail)
- [ ] Test startup with weak secrets (should fail)
- [ ] Test startup with strong secrets (should succeed)
- [ ] Test testing mode with defaults (should succeed)
- [ ] Test error messages are clear and helpful

### Documentation

- [ ] Update `.env.example` with required secrets
- [ ] Add migration guide for developers
- [ ] Document secret generation commands
- [ ] Update deployment documentation
- [ ] Create rollback plan

### Deployment

- [ ] Test on local development environment
- [ ] Deploy to staging
- [ ] Verify staging startup with proper secrets
- [ ] Update CI/CD environment variables
- [ ] Deploy to production
- [ ] Verify production startup
- [ ] Monitor logs for any issues

### Post-Deployment

- [ ] Verify all services started successfully
- [ ] Check error logs for secret validation failures
- [ ] Update team on new requirements
- [ ] Document lessons learned

---

## 🔗 REFERENCES

### Planning Documents
- **Implementation Plan:** `docs/plans/2026-05-07-graxia-implementation-plan.md`
- **Audit Report:** `docs/audits/2026-05-07-graxia-ultra-audit.md`
- **Phase 1 Report:** `docs/phase-reports/PHASE_1_COMPLETION_REPORT.md`

### Code Files
- **Config:** `backend/app/config.py`
- **Event Bus:** `backend/app/core/event_bus.py`
- **Security Middleware:** `backend/app/middleware/security.py`

### External References
- **Alembic Documentation:** https://alembic.sqlalchemy.org/
- **PostgreSQL Indexes:** https://www.postgresql.org/docs/current/indexes.html
- **Asyncio Queue:** https://docs.python.org/3/library/asyncio-queue.html

---

## 📞 CONTACTS

**Phase 2 Lead:** _________________  
**Backend Team:** _________________  
**DBA:** _________________  
**Security Team:** _________________

---

## ✅ READY TO START PHASE 2?

Before starting Phase 2, ensure:

- ✅ Phase 1 is complete and deployed
- ✅ All Phase 1 verification scripts passing
- ✅ Team members assigned to Phase 2 tasks
- ✅ Development environment prepared
- ✅ Sprint planning completed
- ✅ Risks assessed and mitigation plans ready

**If all checkboxes are checked, you're ready to start TASK 2.1!**

---

**Next Step:** Begin TASK 2.1 - Enforce Required Secrets Validation at Startup


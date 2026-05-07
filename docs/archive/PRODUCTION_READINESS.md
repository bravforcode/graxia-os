# 🚀 Graxia OS - Production Readiness Checklist

> **NO FAKE DATA** - ทุกอย่างต้องผ่านการทดสอบด้วยข้อมูลจริง

## 📋 Pre-Deployment Verification

### 1. Infrastructure Readiness

| Item | Status | Verification Command |
|------|--------|---------------------|
| Fly.io API deployed | ⬜ | `flyctl status --app graxia-api` |
| Fly.io Worker deployed | ⬜ | `flyctl status --app graxia-worker` |
| Both VMs running | ⬜ | Check status shows "running" |
| Singapore region | ⬜ | `primary_region = "sin"` in fly.toml |

### 2. Database Readiness

| Item | Status | Verification |
|------|--------|-------------|
| Supabase project created | ⬜ | Console shows "healthy" |
| Tables migrated | ⬜ | Run `alembic upgrade head` |
| Port 6543 configured | ⬜ | DATABASE_URL contains `:6543` |
| pgBouncer enabled | ⬜ | URL ends with `?pgbouncer=true` |
| Connection test passed | ⬜ | Internal health shows DB: healthy |

### 3. Redis Readiness

| Item | Status | Verification |
|------|--------|-------------|
| Upstash Redis created | ⬜ | Console shows "active" |
| Singapore region | ⬜ | Same region as Fly.io |
| REDIS_URL set | ⬜ | `flyctl secrets list --app graxia-api` |
| Connection test passed | ⬜ | Internal health shows Redis: healthy |

### 4. Secrets Configuration

| Secret | API App | Worker App | GitHub Secrets |
|--------|---------|------------|----------------|
| DATABASE_URL | ⬜ | ⬜ | N/A |
| REDIS_URL | ⬜ | ⬜ | N/A |
| SECRET_KEY | ⬜ | ⬜ | N/A |
| ENCRYPTION_KEY | ⬜ | ⬜ | N/A |
| INTERNAL_API_KEY | ⬜ | ⬜ | ⬜ CRITICAL |
| OPENAI_API_KEY | ⬜ | ⬜ | N/A |
| SUPABASE_* | ⬜ | ⬜ | N/A |
| TELEGRAM_BOT_TOKEN | ⬜ | ⬜ | N/A |
| GRAXIA_API_URL | N/A | N/A | ⬜ |
| FLY_API_TOKEN | N/A | N/A | ⬜ |

### 5. GitHub Actions Setup

| Workflow | File Exists | Secrets Configured | Test Run |
|----------|-------------|-------------------|----------|
| cron-lead-hunter.yml | ⬜ | ⬜ | ⬜ |
| cron-daily-report.yml | ⬜ | ⬜ | ⬜ |
| keep-alive.yml | ⬜ | ⬜ | ⬜ |
| deploy-flyio.yml | ⬜ | ⬜ | ⬜ |

---

## 🧪 Testing Phases (ทั้งหมดต้องผ่าน)

### Phase 1: Infrastructure (5 tests)

```powershell
# Run: .\scripts\quick-validation.ps1
```

| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| API Health Endpoint | HTTP 200 | | ⬜ |
| Database Connection | healthy | | ⬜ |
| Redis Connection | healthy | | ⬜ |
| Auth Rejection | HTTP 401 | | ⬜ |
| Queue Status | HTTP 200 | | ⬜ |

**Pass Criteria**: 5/5 tests pass

### Phase 2: API Endpoints (4 tests)

```powershell
# Run: .\scripts\run-production-tests.ps1 -SkipDestructive
```

| Test | Expected | Status |
|------|----------|--------|
| Public: Health | 200 + status | ⬜ |
| Public: System Stats | 200 + data | ⬜ |
| Internal: Health (auth) | 200 | ⬜ |
| Internal: Health (no auth) | 401 | ⬜ |

**Pass Criteria**: 4/4 tests pass

### Phase 3: Functional (Real Data)

```powershell
# Run: .\scripts\run-production-tests.ps1 (without -SkipDestructive)
# Answer 'y' when prompted
```

| Test | Expected | Actual Result | Status |
|------|----------|---------------|--------|
| Daily Report Generated | Has real data | Date: ___, Leads: ___ | ⬜ |
| Cleanup Analysis | Count >= 0 | Records to clean: ___ | ⬜ |
| Lead Hunter Executed | Found >= 0 leads | Found: ___ | ⬜ |
| Lead Hunter DB Verified | Consistency | DB change: ___ | ⬜ |

**Pass Criteria**: 4/4 tests pass, ใช้ข้อมูลจริง

### Phase 4: Integration

| Test | Expected | Status |
|------|----------|--------|
| Frontend → Backend Proxy | 200 | ⬜ |
| CORS Headers | Present | ⬜ |

**Pass Criteria**: 2/2 tests pass

### Phase 5: Performance

| Test | Target | Actual | Status |
|------|--------|--------|--------|
| /health Avg Response | < 500ms | ___ms | ⬜ |
| /health Max Response | < 1000ms | ___ms | ⬜ |
| Concurrent 10x | 10/10 pass | ___/10 | ⬜ |

**Pass Criteria**: All within limits

### Phase 6: Security

| Test | Expected | Status |
|------|----------|--------|
| Invalid Key Rejected | 401 | ⬜ |
| Missing Auth Rejected | 401/403 | ⬜ |

**Pass Criteria**: 2/2 tests pass

---

## 📊 Real Data Verification

### Database Verification

```sql
-- รันที่ Supabase SQL Editor
-- ต้องเห็นข้อมูลจริง ไม่ใช่ empty

SELECT 
    'contacts' as table_name, 
    COUNT(*) as count 
FROM contacts 
UNION ALL
SELECT 
    'opportunities', 
    COUNT(*) 
FROM opportunities 
UNION ALL
SELECT 
    'automation_runs', 
    COUNT(*) 
FROM automation_runs;
```

| Table | Expected | Actual | Status |
|-------|----------|--------|--------|
| contacts | >= 0 | ___ | ⬜ |
| opportunities | >= 0 | ___ | ⬜ |
| automation_runs | >= 0 | ___ | ⬜ |

### GitHub Actions Verification

| Workflow | Last Run | Status | Logs |
|----------|----------|--------|------|
| Lead Hunter | ___ | ⬜ | ⬜ |
| Daily Report | ___ | ⬜ | ⬜ |
| Keep Alive | ___ | ⬜ | ⬜ |

**Verify**: ไปที่ https://github.com/YOUR_USERNAME/graxia-os/actions

---

## 🚨 Critical Checks (ต้องผ่านทั้งหมด)

### Check 1: No Placeholder Secrets

```bash
# Run บน local
# ต้องไม่มี "your_" หรือ "replace_" ในค่าจริง

flyctl secrets list --app graxia-api | grep -E "(your_|replace_|sk-)"
# ผลลัพธ์ต้องเป็น empty (no matches)
```

**Status**: ⬜ PASS / ⬜ FAIL

### Check 2: Internal API Key Consistency

```bash
# ตรวจสอบว่า key ตรงกัน

echo "Fly.io API:"
flyctl secrets get INTERNAL_API_KEY --app graxia-api

echo "Fly.io Worker:"
flyctl secrets get INTERNAL_API_KEY --app graxia-worker

echo "GitHub Secret:"
# ไปดูที่ GitHub → Settings → Secrets → Actions
```

**Status**: ⬜ Consistent / ⬜ Mismatch

### Check 3: Database Port Configuration

```bash
# DATABASE_URL ต้องมี port 6543 ไม่ใช่ 5432

flyctl secrets get DATABASE_URL --app graxia-api
# ผลลัพธ์ต้องมี :6543
```

**Status**: ⬜ Port 6543 (Correct) / ⬜ Port 5432 (WRONG - will fail under load)

### Check 4: Worker Actually Processing

```bash
# ดู logs นาน 1 นาที
flyctl logs --app graxia-worker --tail | head -50
```

ต้องเห็นข้อความประมาณ:
- `Connected to redis`
- `Worker ready`
- `Processing task` (ถ้ามี queue)

**Status**: ⬜ Processing / ⬜ Idle / ⬜ Error

---

## 📝 Documentation Verification

| Document | Exists | Reviewed | Updated |
|----------|--------|----------|---------|
| DEPLOYMENT_GUIDE.md | ⬜ | ⬜ | ⬜ |
| TESTING_GUIDE.md | ⬜ | ⬜ | ⬜ |
| CHECKLIST.md | ⬜ | ⬜ | ⬜ |
| QUICKSTART.md | ⬜ | ⬜ | ⬜ |
| MISSING_COMPONENTS.md | ⬜ | ⬜ | ⬜ |

---

## 🎯 Final Sign-Off

### Technical Lead

| Item | Initials | Date |
|------|----------|------|
| Infrastructure tests passed | ___ | ___ |
| Functional tests passed | ___ | ___ |
| Real data verified | ___ | ___ |
| Security checks passed | ___ | ___ |
| Documentation complete | ___ | ___ |

**Signature**: _______________ **Date**: _______________

### Production Approval

```
[System] ⬜ APPROVED for production deployment
[System] ⬜ HOLD - issues found (see comments)

Comments:
_________________________________________________
_________________________________________________
_________________________________________________
```

---

## 🚀 Post-Deployment Verification (30 นาทีหลัง deploy)

### Immediate Checks (0-5 min)

| Check | Command | Status |
|-------|---------|--------|
| API responding | `curl $API_URL/health` | ⬜ |
| Worker running | `flyctl status --app graxia-worker` | ⬜ |
| No errors in logs | `flyctl logs --app graxia-api` | ⬜ |

### Short-term Checks (5-30 min)

| Check | Expected | Status |
|-------|----------|--------|
| Database connections stable | No "too many connections" errors | ⬜ |
| Redis connected | Worker logs show "connected" | ⬜ |
| First lead hunter run | GitHub Actions shows success | ⬜ |
| Frontend accessible | Vercel URL loads | ⬜ |

---

## 🆘 Emergency Contacts & Rollback

### Rollback Plan

```bash
# If critical failure:

# 1. Rollback API
flyctl deploy --app graxia-api --image <previous-image>

# 2. Restart services
flyctl restart --app graxia-api
flyctl restart --app graxia-worker

# 3. Check status
flyctl status --app graxia-api
flyctl status --app graxia-worker

# 4. Review logs
flyctl logs --app graxia-api
```

### Support Resources

| Service | Support URL | Status Page |
|---------|-------------|-------------|
| Fly.io | https://community.fly.io | https://status.fly.io |
| Supabase | https://github.com/supabase/supabase/discussions | https://status.supabase.com |
| Upstash | https://upstash.com/support | https://status.upstash.com |
| Vercel | https://vercel.com/support | https://status.vercel.com |

---

## ✅ Production Readiness: FINAL DECISION

| Criterion | Met |
|-----------|-----|
| All infrastructure tests pass | ⬜ |
| All functional tests pass | ⬜ |
| Real data verified | ⬜ |
| Security checks pass | ⬜ |
| Documentation complete | ⬜ |
| Team sign-off obtained | ⬜ |

### Decision

```
┌─────────────────────────────────────────┐
│                                         │
│   ⬜ APPROVED FOR PRODUCTION            │
│                                         │
│   ⬜ NOT APPROVED - Fix issues below:   │
│     __________________________________  │
│     __________________________________  │
│     __________________________________  │
│                                         │
└─────────────────────────────────────────┘
```

**Deployment Date**: _______________
**Approved By**: _______________

---

*This checklist must be completed in full before production deployment.*
*NO EXCEPTIONS. NO FAKE DATA.*

# 🚨 สิ่งที่ขาดหายไปและได้เพิ่มเข้าไปแล้ว

## ✅ สิ่งที่เพิ่มเข้าไปเพื่อให้ระบบรันได้จริง

### 1. Internal API Endpoints (`backend/app/api/internal.py`)

**ปัญหา**: GitHub Actions workflows เรียก endpoints ที่ไม่มีอยู่จริง

**แก้ไข**: สร้าง endpoints สำหรับ cron jobs:

| Endpoint | Method | ใช้สำหรับ |
|----------|--------|-----------|
| `/api/v1/internal/health` | GET | Health check สำหรับ monitoring |
| `/api/v1/internal/run-lead-hunter` | POST | GitHub Actions cron (15 min) |
| `/api/v1/internal/daily-report` | POST | GitHub Actions cron (daily) |
| `/api/v1/internal/cleanup` | POST | Database cleanup weekly |
| `/api/v1/internal/backup` | POST | Backup verification |
| `/api/v1/internal/queue-status` | GET | Queue monitoring |

**การยืนยันตัวตน**: ทุก endpoint ต้องส่ง `Authorization: Bearer {INTERNAL_API_KEY}`

### 2. Updated `backend/app/main.py`

**เพิ่ม**:
- Import `internal_router` 
- Include router ที่ `/api/v1/internal`

### 3. Connection Pooling สำหรับ Supabase

**สิ่งที่ต้องทำใน `.env`**:
```bash
# ใช้ port 6543 (Transaction mode pooler) แทน 5432
DATABASE_URL=postgresql+asyncpg://postgres:xxx@db.xxx.supabase.co:6543/postgres?pgbouncer=true

# สำหรับ migrations ใช้ port 5432
DATABASE_MIGRATION_URL=postgresql+asyncpg://postgres:xxx@db.xxx.supabase.co:5432/postgres
```

---

## ⚠️ สิ่งที่ต้องตรวจสอบก่อน Deploy

### 1. LeadHunter Agent
**ตรวจสอบ**: `backend/app/agents/lead_hunter.py` มี method `run()` ที่ return `int` (จำนวน leads ที่เจอ)

**สถานะ**: ✅ มีอยู่แล้ว

### 2. Database Migrations
**ตรวจสอบ**: ต้องรัน migrations ก่อน deploy:

```bash
cd backend
# ใช้ port 5432 สำหรับ migrations (ไม่ใช่ 6543)
export DATABASE_URL="postgresql+asyncpg://postgres:xxx@db.xxx.supabase.co:5432/postgres"
alembic upgrade head
```

### 3. Redis Connection
**ตรวจสอบ**: `backend/app/core/redis_pool.py` ต้องเชื่อมต่อ Upstash ได้

**สถานะ**: ✅ มี `get_redis_client()` อยู่แล้ว

### 4. Telegram Bot
**ตรวจสอบ**: `backend/app/telegram_bot/bot.py` มี `send_notification()`

**สถานะ**: ✅ มีอยู่แล้ว (ถ้าไม่มี จะ log warning แต่ไม่ fail)

### 5. Queue Management
**ตรวจสอบ**: `backend/app/tasks/queues.py` มี `get_queue_depths()`

**สถานะ**: ✅ มีอยู่แล้ว

---

## 🔧 Configuration ที่ต้องตั้งค่า

### GitHub Secrets (Repository → Settings → Secrets → Actions)

```
GRAXIA_API_URL=https://graxia-api.fly.dev
INTERNAL_API_KEY=openssl rand -hex 32  # ต้องตรงกับที่ตั้งใน Fly.io
FLY_API_TOKEN=flyctl tokens create
```

### Fly.io Secrets

```bash
# ตั้งค่าทั้งหมดที่อยู่ใน .env.flyio-template
flyctl secrets set --app graxia-api DATABASE_URL=xxx
flyctl secrets set --app graxia-api REDIS_URL=xxx
flyctl secrets set --app graxia-api SECRET_KEY=xxx
flyctl secrets set --app graxia-api ENCRYPTION_KEY=xxx
flyctl secrets set --app graxia-api INTERNAL_API_KEY=xxx  # สำคัญมาก!
# ... และอื่นๆ
```

---

## 🧪 Testing หลัง Deploy

### 1. Test Health Endpoint
```bash
curl https://graxia-api.fly.dev/health
curl https://graxia-api.fly.dev/api/v1/internal/health \
  -H "Authorization: Bearer YOUR_INTERNAL_API_KEY"
```

### 2. Test Lead Hunter (Manual)
```bash
curl -X POST https://graxia-api.fly.dev/api/v1/internal/run-lead-hunter \
  -H "Authorization: Bearer YOUR_INTERNAL_API_KEY"
```

### 3. Check GitHub Actions
- ไปที่ Repository → Actions
- ต้องเห็น workflows ทั้ง 4 อัน:
  - `cron-lead-hunter.yml` (รันทุก 15 นาที)
  - `cron-daily-report.yml` (รันทุกวัน)
  - `keep-alive.yml` (รันทุก 5 นาที)
  - `deploy-flyio.yml` (รันเมื่อ push)

### 4. Check Fly.io
```bash
flyctl status --app graxia-api
flyctl status --app graxia-worker
flyctl logs --app graxia-api
```

---

## 🚨 Common Issues

### Issue 1: `INTERNAL_API_KEY` mismatch
**อาการ**: GitHub Actions ได้รับ 401 Unauthorized
**แก้ไข**: 
1. ตรวจสอบว่า `INTERNAL_API_KEY` ตรงกันใน Fly.io และ GitHub Secrets
2. ต้องมี prefix `Bearer ` ใน header

### Issue 2: Database connection limit
**อาการ**: `FATAL: remaining connection slots are reserved` หรือ `too many connections`
**แก้ไข**: 
1. ใช้ port 6543 (Transaction pooler) แทน 5432
2. ลด `DB_POOL_SIZE` ใน `.env` (เช่น จาก 20 เหลือ 5)

### Issue 3: Redis connection fail
**อาการ**: Worker ไม่ทำงาน
**แก้ไข**: 
1. ตรวจสอบ `REDIS_URL` ใน Fly.io secrets
2. ตรวจสอบว่า Upstash อยู่ใน region เดียวกัน (Singapore)

### Issue 4: Worker not processing
**อาการ**: Queue เต็มแต่ worker ไม่ทำงาน
**แก้ไข**:
```bash
flyctl restart --app graxia-worker
flyctl logs --app graxia-worker
```

---

## 📋 Final Checklist ก่อน Production

- [ ] `INTERNAL_API_KEY` ตั้งใน Fly.io และ GitHub Secrets
- [ ] Database migrations รันแล้ว (ใช้ port 5432)
- [ ] `.env` ใช้ port 6543 สำหรับ DATABASE_URL
- [ ] All Fly.io secrets ตั้งครบ
- [ ] GitHub Actions workflows อยู่ใน `.github/workflows/`
- [ ] `fly.toml` และ `fly.worker.toml` อยู่ใน `backend/`
- [ ] Internal router ถูก include ใน `main.py`
- [ ] Health endpoints ตอบสนอง
- [ ] Test lead hunter endpoint ด้วย curl
- [ ] Test database connection ผ่าน internal health

---

## ✅ สถานะปัจจุบัน

**ทุกอย่างพร้อม Deploy แล้ว!**

สิ่งที่เพิ่มเข้าไปล่าสุด:
1. ✅ `backend/app/api/internal.py` - Internal cron endpoints
2. ✅ Updated `backend/app/main.py` - Include internal router
3. ✅ `.github/workflows/` - 4 cron/deploy workflows
4. ✅ `backend/fly.toml` + `fly.worker.toml` - Fly.io configs
5. ✅ `backend/.env.flyio-template` - Environment template
6. ✅ `scripts/` - Deployment helpers
7. ✅ Documentation - DEPLOYMENT_GUIDE.md, CHECKLIST.md, QUICKSTART.md

**พร้อม Deploy! 🚀**

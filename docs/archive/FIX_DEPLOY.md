# 🔧 FIX DEPLOY - API Stopped

## สถานะปัญหา
```
graxia-api: stopped, 1 warning, failed health checks
graxia-worker: starting ✓
```

## ขั้นตอนแก้ไข

### Step 1: ดู Logs หาสาเหตุ

```powershell
# ดู logs ล่าสุด 50 บรรทัด
flyctl logs --app graxia-api --tail

# หรือดูทั้งหมด
flyctl logs --app graxia-api
```

**ค้นหาข้อความประมาณนี้:**
- `Error:` หรือ `Exception:`
- `Failed to connect`
- `ModuleNotFoundError`
- `Connection refused`
- `timeout`

### Step 2: Common Fixes

#### ปัญหา A: Database Connection Failed
**อาการ**: `could not connect to database` หรือ `connection refused`

**แก้ไข**:
```powershell
# ตรวจสอบ secrets ว่าตั้งถูกหรือไม่
flyctl secrets list --app graxia-api

# ถ้าผิด ให้ reset
flyctl secrets set --app graxia-api DATABASE_URL="postgresql+asyncpg://postgres:Q5HkxsiINJSPy7vN@db.eezrhwiwwsmarkvejeoi.supabase.co:6543/postgres?pgbouncer=true"
```

#### ปัญหา B: Missing Python Modules
**อาการ**: `ModuleNotFoundError: No module named 'xxx'`

**แก้ไข**:
```powershell
# requirements.txt อาจขาดบางอย่าง
# แก้ไขแล้ว redeploy
cd backend
flyctl deploy --config fly.toml --remote-only
```

#### ปัญหา C: Port Mismatch
**อาการ**: `port already in use` หรือ `cannot bind to port`

**แก้ไข**: ตรวจสอบ `fly.toml`
```toml
[env]
PORT = "8080"  # ต้องตรงกับที่ app ใช้

[http_service]
internal_port = 8080  # ต้องตรงกับ PORT
```

#### ปัญหา D: Health Check Timeout
**อาการ**: `timeout reached waiting for health checks`

**แก้ไข**: เพิ่ม grace period
```toml
[[http_service.checks]]
grace_period = "10s"  # เพิ่มจาก 5s เป็น 10s
interval = "30s"
timeout = "10s"  # เพิ่มจาก 5s เป็น 10s
```

### Step 3: Restart & Redeploy

```powershell
# 1. Restart API
flyctl restart --app graxia-api

# 2. รอ 30 วินาที
Start-Sleep -Seconds 30

# 3. เช็ค status
flyctl status --app graxia-api

# 4. ถ้ายังไม่ผ่าน redeploy
flyctl deploy --config fly.toml --remote-only --wait-timeout=10m
```

### Step 4: SSH เข้าไป Debug (ถ้าจำเป็น)

```powershell
# SSH เข้าไปดูข้างใน
flyctl ssh console --app graxia-api

# แล้วรันคำสั่งดู logs หรือ test
ls -la
cat /app/logs/*.log 2>/dev/null || echo "no logs"
python -c "from app.main import app; print('import ok')"
```

### Step 5: Test Local ก่อน

```powershell
# Test ว่า app รันได้บน local หรือไม่
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# แล้วเปิดอีก terminal
curl http://localhost:8000/health
```

ถ้า local ไม่ผ่าน → ปัญหาใน code ไม่ใช่ Fly.io

---

## 🧪 Quick Tests

### Test 1: Health Check (ถ้า API รันอยู่)
```powershell
curl https://graxia-api.fly.dev/health
curl https://graxia-api.fly.dev/api/v1/system/health
```

### Test 2: ดูว่า Machine รันไหม
```powershell
flyctl machines list --app graxia-api
```

ถ้าเห็น `stopped` → ต้อง start
```powershell
flyctl machines start --app graxia-api
```

---

## 🚨 Nuclear Option (ถ้าทุกอย่างล้มเหลว)

```powershell
# ลบแล้วสร้างใหม่
flyctl apps destroy graxia-api
flyctl apps create graxia-api

# ตั้ง secrets ใหม่
flyctl secrets set --app graxia-api INTERNAL_API_KEY="$env:INTERNAL_API_KEY"
flyctl secrets set --app graxia-api DATABASE_URL="postgresql+asyncpg://postgres:Q5HkxsiINJSPy7vN@db.eezrhwiwwsmarkvejeoi.supabase.co:6543/postgres?pgbouncer=true"
flyctl secrets set --app graxia-api REDIS_URL="rediss://default:91cMDMcnEeBMjmz9p7PZLPsiZ7C3edzW@redis-18128.c295.ap-southeast-1-1.ec2.cloud.redislabs.com:18128"

# Deploy ใหม่
flyctl deploy --config fly.toml --remote-only
```

---

## ✅ Success Criteria

```powershell
flyctl status --app graxia-api
# ต้องเห็น:
# STATE: running
# CHECKS: 1 total, 1 passing
```

แล้วทดสอบ:
```powershell
curl https://graxia-api.fly.dev/health
# ต้องได้ {"status":"ok"} หรืออะไรก็ตามที่ไม่ใช่ error
```

---

**เริ่มจาก Step 1: ดู logs ก่อน!**

# 🚀 DEPLOY NOW - ขั้นตอน Deploy จริง

> ทดสอบไม่ได้เพราะยังไม่ได้ Deploy! ทำตามนี้ก่อน

## ⚡ Quick Deploy (5 นาที)

### 1. ตรวจสอบ Prerequisites

```powershell
# ตรวจสอบว่า flyctl ติดตั้งแล้ว
flyctl version

# ถ้ายังไม่มี ติดตั้งก่อน
# (New-Object Net.WebClient).DownloadString("https://fly.io/install.ps1") | Invoke-Expression

# Login
flyctl auth login
```

### 2. สร้าง Apps บน Fly.io

```powershell
cd backend

# สร้าง app (ถ้ายังไม่มี)
flyctl apps create graxia-api
flyctl apps create graxia-worker
```

### 3. ตั้ง Secrets (สำคัญที่สุด!)

```powershell
cd backend

# สร้าง .env จาก template ก่อน (ถ้ายังไม่มี)
# แก้ไขไฟล์ .env ให้มีค่าจริงทั้งหมด

# จากนั้นตั้ง secrets บน Fly.io:
flyctl secrets set --app graxia-api DATABASE_URL="postgresql+asyncpg://postgres:PASSWORD@db.REF.supabase.co:6543/postgres?pgbouncer=true"
flyctl secrets set --app graxia-api REDIS_URL="redis://default:PASSWORD@ENDPOINT:6379"
flyctl secrets set --app graxia-api SECRET_KEY="$(openssl rand -hex 32)"
flyctl secrets set --app graxia-api INTERNAL_API_KEY="$(openssl rand -hex 32)"
# ... และอื่นๆ ตาม .env.flyio-template

# ตั้งให้ worker ด้วย
flyctl secrets set --app graxia-worker DATABASE_URL="..."
flyctl secrets set --app graxia-worker REDIS_URL="..."
# ... (ค่าเดียวกับ API)
```

**💡 วิธีง่าย**: ใช้ script ที่สร้างไว้แล้ว
```powershell
cd ..
.\scripts\setup-complete.sh  # หรือ setup-secrets.sh
```

### 4. Deploy

```powershell
cd backend

# Deploy API
flyctl deploy --config fly.toml --remote-only

# Deploy Worker
flyctl deploy --config fly.worker.toml --remote-only
```

### 5. ตรวจสอบ Status

```powershell
flyctl status --app graxia-api
flyctl status --app graxia-worker

# ดู logs
flyctl logs --app graxia-api
```

**สำเร็จเมื่อเห็น**: `v1 deployed successfully` และ status เป็น `running`

---

## 🧪 หลัง Deploy สำเร็จ ค่อยทดสอบ

### Step 1: เก็บ INTERNAL_API_KEY

```powershell
# ดู key ที่ตั้งไว้ (บันทึกไว้ใช้ทดสอบ)
flyctl secrets get INTERNAL_API_KEY --app graxia-api

# ตั้ง environment variable
$env:INTERNAL_API_KEY = "key-ที่ได้มา"
```

### Step 2: ทดสอบ

```powershell
# ทดสอบเร็ว
.\scripts\quick-validation.ps1

# ทดสอบเต็ม
.\scripts\run-production-tests.ps1
```

---

## 🔍 ตรวจสอบว่า Deploy สำเร็จหรือไม่

### วิธีที่ 1: curl
```powershell
curl https://graxia-api.fly.dev/health
# ต้องได้: {"status": "ok"} หรืออะไรก็ตามที่ไม่ใช่ "No such host"
```

### วิธีที่ 2: browser
เปิด browser ไปที่: `https://graxia-api.fly.dev/health`

### วิธีที่ 3: flyctl
```powershell
flyctl status --app graxia-api
# ต้องเห็น: 1 desired, 1 placed, 1 healthy, 0 unhealthy
```

---

## ⚠️ ถ้าเจอปัญหา

### ปัญหา: "No such host is known"
**สาเหตุ**: ยังไม่ได้สร้าง app หรือ deploy
**แก้ไข**: ทำ Step 1-4 ด้านบน

### ปัญหา: "failed to fetch an image or build from source"
**สาเหตุ**: Dockerfile มีปัญหา
**แก้ไข**: 
```powershell
cd backend
flyctl deploy --config fly.toml --remote-only --build-only
```

### ปัญหา: "error connecting to database"
**สาเหตุ**: DATABASE_URL ผิด หรือ Supabase ยังไม่พร้อม
**แก้ไข**: 
1. ตรวจสอบ Supabase connection string
2. ใช้ port 6543 (ไม่ใช่ 5432)
3. ตรวจสอบว่า Supabase project อยู่ใน region Singapore

---

## ✅ สรุปสิ่งที่ต้องทำก่อน Testing

- [ ] Deploy API บน Fly.io สำเร็จ
- [ ] Deploy Worker บน Fly.io สำเร็จ
- [ ] ได้ INTERNAL_API_KEY ที่ตั้งบน Fly.io
- [ ] curl https://graxia-api.fly.dev/health ตอบสนอง
- [ ] ตั้ง `$env:INTERNAL_API_KEY` บน local machine
- [ ] ค่อยรัน testing scripts

**ยังไม่พร้อม testing ตอนนี้ - ต้อง Deploy ก่อน!**

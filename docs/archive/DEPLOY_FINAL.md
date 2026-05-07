# 🚀 FINAL DEPLOY - ขั้นตอนสุดท้าย

> Secrets พร้อมแล้ว! Deploy ตอนนี้เลย

## ⚡ คำสั่ง Deploy (Copy ทั้งก้อนแล้วรัน)

```powershell
# ============================================
# STEP 1: ตั้ง Secrets บน Fly.io
# ============================================

# Internal API Key (จากที่ generate มา)
flyctl secrets set --app graxia-api INTERNAL_API_KEY="$env:INTERNAL_API_KEY"
flyctl secrets set --app graxia-worker INTERNAL_API_KEY="$env:INTERNAL_API_KEY"

# Database (แก้เป็น asyncpg format + pgbouncer)
flyctl secrets set --app graxia-api DATABASE_URL="postgresql+asyncpg://postgres:Q5HkxsiINJSPy7vN@db.eezrhwiwwsmarkvejeoi.supabase.co:6543/postgres?pgbouncer=true"
flyctl secrets set --app graxia-worker DATABASE_URL="postgresql+asyncpg://postgres:Q5HkxsiINJSPy7vN@db.eezrhwiwwsmarkvejeoi.supabase.co:6543/postgres?pgbouncer=true"

# Redis
flyctl secrets set --app graxia-api REDIS_URL="rediss://default:91cMDMcnEeBMjmz9p7PZLPsiZ7C3edzW@redis-18128.c295.ap-southeast-1-1.ec2.cloud.redislabs.com:18128"
flyctl secrets set --app graxia-worker REDIS_URL="rediss://default:91cMDMcnEeBMjmz9p7PZLPsiZ7C3edzW@redis-18128.c295.ap-southeast-1-1.ec2.cloud.redislabs.com:18128"

# ============================================
# STEP 2: Deploy
# ============================================

cd backend

# Deploy API
flyctl deploy --config fly.toml --remote-only

# Deploy Worker (รอให้ API deploy เสร็จก่อน ค่อยรัน)
flyctl deploy --config fly.worker.toml --remote-only

# ============================================
# STEP 3: ตรวจสอบ
# ============================================

flyctl status --app graxia-api
flyctl status --app graxia-worker

Write-Host "✅ Deploy สำเร็จ!" -ForegroundColor Green
Write-Host "ทดสอบ: curl https://graxia-api.fly.dev/health" -ForegroundColor Cyan
```

---

## 🔍 ตรวจสอบว่า Deploy สำเร็จ

```powershell
# Test 1: Health check
curl https://graxia-api.fly.dev/health

# ต้องได้ประมาณนี้:
# {"status":"ok",...}

# Test 2: ด้วย Internal Key
.\scripts\quick-validation.ps1
```

---

## ⚠️ ถ้าเจอปัญหา

### "app not found"
```powershell
# สร้าง app ก่อน
flyctl apps create graxia-api
flyctl apps create graxia-worker
```

### "failed to fetch an image"
```powershell
# ดู logs ว่า build ผิดตรงไหน
flyctl deploy --config fly.toml --remote-only --build-only
```

### "connection refused"
```powershell
# รอสักครู่แล้วลองใหม่ (Fly.io กำลัง start)
Start-Sleep -Seconds 30
flyctl status --app graxia-api
```

---

## 🎯 หลัง Deploy สำเร็จ

1. **ตั้ง GitHub Secrets** (สำหรับ Actions):
   - ไปที่ https://github.com/YOUR_USERNAME/graxia-os/settings/secrets/actions
   - Add `GRAXIA_API_URL`: `https://graxia-api.fly.dev`
   - Add `INTERNAL_API_KEY`: (paste จาก clipboard)
   - Add `FLY_API_TOKEN`: (รัน `flyctl tokens create`)

2. **ทดสอบ**:
   ```powershell
   .\scripts\quick-validation.ps1
   ```

3. **เช็ค GitHub Actions**:
   - ไปที่ https://github.com/YOUR_USERNAME/graxia-os/actions
   - ดูว่า workflows ทำงานหรือไม่

---

**พร้อม Deploy! รันคำสั่งข้างบนเลย 🚀**

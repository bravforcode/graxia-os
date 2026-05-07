# 🔑 วิธีหา Secrets สำหรับ Deploy

## 1. DATABASE_URL (จาก Supabase)

### Step-by-Step:

1. **ไปที่ Supabase Dashboard**
   - URL: https://app.supabase.com
   - เข้า project ของคุณ

2. **ไปที่ Settings → Database**
   - คลิก "Settings" ด้านล่างซ้าย
   - เลือก "Database"

3. **หา Connection String**
   - ดูที่ "Connection string"
   - เลือก **"Transaction mode"** (port 6543) ❗สำคัญ
   - อย่าใช้ "Session mode" (port 5432)

4. **Format ที่ถูกต้อง:**
```
postgresql+asyncpg://postgres:[PASSWORD]@db.[PROJECT_REF].supabase.co:6543/postgres?pgbouncer=true
```

**ตัวอย่าง:**
```
postgresql+asyncpg://postgres:MySecretPassword123@db.abc123xyz.supabase.co:6543/postgres?pgbouncer=true
```

### สิ่งที่ต้องเปลี่ยน:
- `[PASSWORD]` → password ที่ตั้งตอนสร้าง project
- `[PROJECT_REF]` → อยู่ใน URL ของ project (เช่น abc123xyz)

### ตรวจสอบ:
- ✅ มี `:6543` (port 6543)
- ✅ ลงท้ายด้วย `?pgbouncer=true`
- ✅ ไม่มี `[]` หรือ `<>` ในค่าจริง
- ❌ ไม่ใช่ port 5432

---

## 2. INTERNAL_API_KEY (สร้างเอง)

### วิธี Generate:

```powershell
# ใน PowerShell
openssl rand -hex 32
```

**ผลลัพธ์ตัวอย่าง:**
```
a3f7c8d9e2b1a4f5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8
```

### หรือถ้าไม่มี openssl:
```powershell
# ใช้ .NET
[Convert]::ToHexString((1..32 | ForEach-Object { Get-Random -Max 256 } | ForEach-Object { [byte]$_ }))
```

### คุณสมบัติ:
- 64 ตัวอักษร (32 bytes)
- สุ่ม ไม่ซ้ำใคร
- เก็บไว้ใช้ทั้งใน Fly.io + GitHub

---

## 3. SECRET_KEY (สร้างเอง)

```powershell
openssl rand -hex 32
# หรือ
openssl rand -hex 64
```

---

## 4. ENCRYPTION_KEY (สร้างจาก Python)

```powershell
# ต้องมี Python ติดตั้ง
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**ผลลัพธ์ตัวอย่าง:**
```
gAAAAABfJ7X8Z3QxJvL8x2vT... (44 ตัวอักษร base64)
```

---

## 5. ค่าอื่นๆ ที่ต้องมี

### SUPABASE_URL:
```
https://[PROJECT_REF].supabase.co
```
ตัวอย่าง: `https://abc123xyz.supabase.co`

### SUPABASE_ANON_KEY:
- อยู่ใน Supabase → Settings → API → "anon public"

### SUPABASE_SERVICE_ROLE_KEY:
- อยู่ใน Supabase → Settings → API → "service_role" (secret)

### OPENAI_API_KEY:
- ไปที่ https://platform.openai.com/api-keys
- สร้าง new secret key

### TELEGRAM_BOT_TOKEN:
- คุยกับ @BotFather บน Telegram
- สร้าง bot ใหม่ → ได้ token

### TELEGRAM_CHAT_ID:
1. ส่งข้อความให้ bot
2. เปิด: https://api.telegram.org/bot[BOT_TOKEN]/getUpdates
3. ดู "chat" → "id"

---

## 📝 สรุปคำสั่งที่ต้องรัน

```powershell
# 1. Generate keys
$INTERNAL_KEY = openssl rand -hex 32
$SECRET_KEY = openssl rand -hex 64

Write-Host "INTERNAL_API_KEY: $INTERNAL_KEY"
Write-Host "SECRET_KEY: $SECRET_KEY"

# 2. ตั้งบน Fly.io (API)
flyctl secrets set --app graxia-api INTERNAL_API_KEY="$INTERNAL_KEY"
flyctl secrets set --app graxia-api SECRET_KEY="$SECRET_KEY"
flyctl secrets set --app graxia-api DATABASE_URL="postgresql+asyncpg://postgres:YOUR_PASSWORD@db.YOUR_REF.supabase.co:6543/postgres?pgbouncer=true"

# 3. ตั้งบน Fly.io (Worker) - ค่าเดียวกัน
flyctl secrets set --app graxia-worker INTERNAL_API_KEY="$INTERNAL_KEY"
flyctl secrets set --app graxia-worker SECRET_KEY="$SECRET_KEY"
flyctl secrets set --app graxia-worker DATABASE_URL="..."

# 4. บันทึกไว้ใช้ทดสอบ
$env:INTERNAL_API_KEY = "$INTERNAL_KEY"
Write-Host "บันทึก INTERNAL_API_KEY สำหรับ testing แล้ว"
```

---

## ⚠️ ข้อควรระวัง

1. **อย่า commit secrets ขึ้น GitHub**
   - `.env` ต้องอยู่ใน `.gitignore`
   - ใช้ `flyctl secrets` เท่านั้น

2. **INTERNAL_API_KEY ต้องตรงกัน**
   - Fly.io API app = Fly.io Worker app = GitHub Secrets

3. **DATABASE_URL ต้องมี port 6543**
   - Port 5432 จะทำให้เกิน connection limit

4. **เก็บ keys ไว้ที่ปลอดภัย**
   - สร้างไฟล์ `secrets.txt` แล้ว encrypt
   - หรือใช้ password manager

---

## ✅ Checklist ก่อน Deploy

- [ ] DATABASE_URL ได้จาก Supabase (port 6543)
- [ ] INTERNAL_API_KEY สร้างแล้ว (64 ตัวอักษร)
- [ ] SECRET_KEY สร้างแล้ว
- [ ] ENCRYPTION_KEY สร้างแล้ว
- [ ] SUPABASE_* keys ได้จาก dashboard
- [ ] OPENAI_API_KEY มีแล้ว
- [ ] TELEGRAM_BOT_TOKEN + CHAT_ID มีแล้ว (optional)
- [ ] ตั้ง secrets ทั้งหมดบน Fly.io แล้ว
- [ ] เก็บ INTERNAL_API_KEY ไว้ใช้ทดสอบ

**พร้อม Deploy! 🚀**

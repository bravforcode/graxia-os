# Graxia OS — Complete Setup Guide
## วิธีการขอ API Keys ทั้งหมดอย่างละเอียด

---

## 1. Telegram Bot (สำหรับแจ้งเตือนและ Approve)

### ขั้นตอนที่ 1: สร้าง Bot ผ่าน @BotFather
1. เปิด Telegram และค้นหา `@BotFather`
2. กด `/start` แล้วเลือก `/newbot`
3. ตั้งชื่อ bot (เช่น `GraxiaOS Bot`)
4. ตั้ง username สำหรับ bot (ต้องลงท้ายด้วย bot เช่น `graxiaos_bot`)
5. บันทึก **Bot Token** ที่ได้รับ (รูปแบบ: `123456789:ABCdefGHIjklMNOpqrSTUvwxyz`)

### ขั้นตอนที่ 2: หา Chat ID
1. ค้นหา `@userinfobot` ใน Telegram
2. กด `/start` แล้วส่งข้อความอะไรก็ได้
3. บอทจะตอบกลับด้วยข้อมูลของคุณ ให้บันทึกตัวเลข **ID** (เช่น `123456789`)

**หรือ** ถ้าใช้ Group:
1. เพิ่ม bot เข้าไปใน group
2. ส่งข้อความ `/test` ใน group
3. เปิด browser ไปที่: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
4. หา chat.id ใน JSON response

### ใส่ใน .env:
```bash
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxyz
TELEGRAM_CHAT_ID=123456789
```

---

## 2. Stripe (สำหรับรับเงินบัตรเครดิต)

### ขั้นตอนที่ 1: สมัคร Stripe Account
1. ไปที่ https://dashboard.stripe.com/register
2. สมัคร account ด้วย email และยืนยัน
3. กรอกข้อมูลธุรกิจ (ใช้ข้อมูลจริงเพื่อรับเงินได้)

### ขั้นตอนที่ 2: เอา API Keys
1. ไปที่ https://dashboard.stripe.com/apikeys
2. คลิก "Reveal test key" หรือ "Create secret key"
3. บันทึก **Secret key** (รูปแบบ: `sk_test_...` หรือ `sk_live_...`)
4. บันทึก **Publishable key** (รูปแบบ: `pk_test_...` หรือ `pk_live_...`)

### ขั้นตอนที่ 3: สร้าง Webhook
1. ไปที่ https://dashboard.stripe.com/webhooks
2. คลิก "Add endpoint"
3. Endpoint URL: `https://yourdomain.com/api/v1/revenue/webhooks/stripe`
4. เลือก Events:
   - `checkout.session.completed`
   - `invoice.payment_succeeded`
   - `customer.subscription.created`
   - `charge.refunded`
5. คลิก "Add endpoint"
6. คลิกที่ endpoint ที่สร้างแล้ว ไปที่ "Signing secret"
7. บันทึก **Webhook signing secret** (รูปแบบ: `whsec_...`)

### ใส่ใน .env:
```bash
STRIPE_SECRET_KEY=sk_live_xxxxxxxxxxxxxxxxx
STRIPE_PUBLISHABLE_KEY=pk_live_xxxxxxxxxxxxxxxxx
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxxx
```

---

## 3. MetaTrader 5 (สำหรับเทรด Forex)

### ขั้นตอนที่ 1: ติดตั้ง MT5
1. ดาวน์โหลด MT5 จาก https://www.metatrader5.com/
2. ติดตั้งและเปิดโปรแกรม

### ขั้นตอนที่ 2: สร้าง Demo Account (สำหรับทดสอบ)
1. ใน MT5 ไปที่ File > Open an Account
2. เลือก broker (แนะนำ IC Markets, Oanda, หรือ FXCM)
3. เลือก "New Demo Account"
4. กรอกข้อมูลและบันทึก:
   - **Login** (ตัวเลข เช่น `12345678`)
   - **Password** 
   - **Server** (เช่น `ICMarketsSC-Demo`, `Oanda-Demo`)

### ขั้นตอนที่ 3: หรือใช้ Live Account (สำหรับเทรดจริง)
1. เปิดบัญชีกับ broker ที่รองรับ MT5
2. รับ Login, Password, และ Server จาก broker
3. ฝากเงินเข้าบัญชี

### ใส่ใน .env:
```bash
TRADING_MODE=PAPER  # หรือ LIVE
LIVE_TRADING_ENABLED=false  # เปลี่ยนเป็น true ถ้าใช้ Live
MT5_LOGIN=12345678
MT5_PASSWORD=your_mt5_password
MT5_SERVER=ICMarketsSC-Demo
```

---

## 4. Redis (สำหรับ Cache และ Celery)

### Option A: ใช้ Redis Local (Docker)
```bash
docker run -d -p 6379:6379 --name redis redis:7-alpine
```

### Option B: ใช้ Redis Cloud (Upstash - Free)
1. ไปที่ https://upstash.com/
2. สมัคร account
3. สร้าง Redis database
4. บันทึก **Redis URL** (รูปแบบ: `rediss://default:password@host:port`)

### Option C: ใช้ Railway/Render
- Railway: https://railway.app/
- Render: https://render.com/

### ใส่ใน .env:
```bash
REDIS_URL=redis://localhost:6379/0
# หรือ
REDIS_URL=rediss://default:xxx@xxx.upstash.io:6379/0
```

---

## 5. PostgreSQL Database (สำหรับเก็บข้อมูล)

### Option A: Local Docker
```bash
docker run -d -p 5432:5432 \
  -e POSTGRES_USER=graxia \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=graxia \
  --name postgres \
  postgres:15-alpine
```

### Option B: Supabase (Free Tier)
1. ไปที่ https://supabase.com/
2. สมัคร account และสร้าง project
3. ไปที่ Settings > Database
4. บันทึก **Connection string** (รูปแบบ: `postgresql://postgres:password@host:5432/postgres`)

### Option C: Neon (Free Tier)
1. ไปที่ https://neon.tech/
2. สมัคร account และสร้าง project
3. ไปที่ Connection Details
4. บันทึก connection string

### ใส่ใน .env:
```bash
DATABASE_URL=postgresql+asyncpg://graxia:password@localhost:5432/graxia
# สำหรับ Supabase/Neon
DATABASE_URL=postgresql+asyncpg://postgres:xxx@xxx.supabase.co:5432/postgres
```

---

## 6. Security Keys (สร้างอัตโนมัติ)

### วิธีสร้าง:
```bash
cd graxia-os
python scripts/generate_keys.py
```

### หรือสร้างเอง:
```bash
# Linux/Mac
openssl rand -hex 32

# Windows PowerShell
[Convert]::ToHexString((1..32 | ForEach-Object { Get-Random -Max 256 } | ForEach-Object { [byte]$_ }))
```

### ใส่ใน .env:
```bash
JWT_SECRET_KEY=your_random_32_char_string_here
ADMIN_API_KEY=your_admin_api_key_here
WEBHOOK_HMAC_SECRET=your_webhook_secret_here
```

---

## 7. สรุป .env ที่สมบูรณ์

```bash
# ==========================================
# GRAXIA OS — Environment Configuration
# ==========================================

# Database
DATABASE_URL=postgresql+asyncpg://graxia:password@localhost:5432/graxia

# Redis
REDIS_URL=redis://localhost:6379/0

# Security (สร้างด้วย scripts/generate_keys.py)
JWT_SECRET_KEY=change_me_32_char_minimum
ADMIN_API_KEY=change_me_32_char_minimum
WEBHOOK_HMAC_SECRET=change_me_32_char_minimum

# Telegram Notifications
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxyz
TELEGRAM_CHAT_ID=123456789

# Stripe Payments
STRIPE_SECRET_KEY=sk_test_xxxxxxxxxxxxxxxxx
STRIPE_PUBLISHABLE_KEY=pk_test_xxxxxxxxxxxxxxxxx
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxxx

# MetaTrader 5 Trading
TRADING_MODE=PAPER
LIVE_TRADING_ENABLED=false
MT5_LOGIN=12345678
MT5_PASSWORD=your_password
MT5_SERVER=ICMarketsSC-Demo

# CORS (สำหรับ Web UI)
CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# Logging
LOG_LEVEL=INFO
```

---

## 8. ตรวจสอบการตั้งค่า

```bash
python scripts/check_env.py
```

ถ้าผ่านทั้งหมดจะขึ้น:
```
✓ All required keys configured!
```

---

## 9. เริ่มต้นระบบ

```bash
# Windows
scripts\start_unified.bat

# Linux/Mac
bash scripts/deploy.sh
```

---

## 10. ทดสอบระบบ

```bash
# รัน brutal tests
python scripts/brutal_test.py

# ทดสอบ API
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/status
```

---

## การสนับสนุน

หากมีปัญหา:
1. ตรวจสอบ logs: `docker logs graxia-os-api`
2. ตรวจสอบ env: `python scripts/check_env.py`
3. เปิด issue ใน GitHub

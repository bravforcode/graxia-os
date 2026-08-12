# DEPLOY CHECKLIST — Ai Factory (Vercel-native, $0/เดือน)

> อัปเดต: 2026-08-12 — ย้ายจาก Render เป็น **Vercel + Neon + cron-job.org** (ค่าใช้จ่าย $0)
> โค้ดผ่านการตรวจแล้ว: funnel tests เขียว (~110 ตัว) + slim store API smoke test ผ่าน

## สถาปัตยกรรมใหม่

```
[Vercel — $0]                              [Neon — $0]        [cron-job.org — $0]
├── frontend/ (Vite, live อยู่แล้ว)        Postgres + pgvector   ping ทุก 15 นาที
└── api/store_main.py (Python function) ──→ DB ──→ automation scans
    ├── /api/v1/*  (สินค้า, checkout, delivery, lead magnets, analytics)
    ├── /api/v1/funnel/webhooks/stripe  (Stripe → ระบบ)
    └── /internal/funnel/process-due    (cron bridge, X-Internal-Token)
```

**อะไรที่ไม่ทำงานบน Vercel (โดยตั้งใจ):**
- ❌ WebSockets (`/v1/graxia/stream`, `/ai/ws`) — ฟีเจอร์ Graxia AI ที่ปิดไว้อยู่แล้ว (`GRAXIA_ENABLED=false`)
- ❌ Celery workers — แทนด้วย `funnel_automation_runtime.py` (scan ตรงจาก DB) รันผ่าน cron-job.org ping
- ❌ งานหนัก (scrapers/ML/graphql) — ไม่ mount ใน slim app (`api/store_main.py`)

---

## ขั้นตอน

### 1. สมัคร Neon (ฟรี) — 2 นาที
1. https://neon.tech → Sign up (GitHub login ได้) → New project (region เลือกใกล้ไทย: Singapore/Tokyo)
2. เปิด Database → **Connection string** → เลือก tab **Pooled connection** (`-pooler.neon.tech`)
3. คัดลอก URL (รูปแบบ `postgresql://user:pass@ep-xxx-pooler.neon.tech/neondb?sslmode=require`)
4. ⚠️ แปลงเป็น asyncpg: เปลี่ยน `postgresql://` → `postgresql+asyncpg://`

### 2. Stripe — สร้าง key ใหม่ (key เก่าหมดอายุแล้ว)
1. https://dashboard.stripe.com/apikeys → **Create secret key** (เริ่มจาก test mode: `sk_test_...`)
2. (ทีหลัง) Webhooks → Add endpoint: `https://<project>.vercel.app/api/v1/funnel/webhooks/stripe`
   - Events: `checkout.session.completed`, `checkout.session.expired` → ได้ `whsec_...`

### 3. ตั้ง env บน Vercel
```bash
vercel link            # เชื่อม repo กับโปรเจกต์ที่มีอยู่
vercel env add DATABASE_URL production
vercel env add STRIPE_SECRET_KEY production
vercel env add RESEND_API_KEY production      # มีแล้ว (ส่งอีเมลได้ ✅)
vercel env add SECRET_KEY production          # ค่าใน .env.production
vercel env add ENCRYPTION_KEY production
vercel env add CSRF_SECRET production
vercel env add ADMIN_API_KEY production
vercel env add INTERNAL_METRICS_TOKEN production
vercel env add ADMIN_DEFAULT_EMAIL production   # admin@graxia.store
vercel env add ADMIN_DEFAULT_PASSWORD production
vercel env add FRONTEND_URL production        # https://graxia-os-funnel.vercel.app
vercel env add ALLOWED_CORS_ORIGINS production
vercel env add APP_ENV production
vercel env add DB_POOL_SIZE production         # 1
vercel env add DB_MAX_OVERFLOW production      # 1
```

### 4. Deploy
```bash
git push origin main        # Vercel auto-deploy ผ่าน GitHub integration
# หรือ manual:
vercel deploy --prod
```

### 5. Migration (รันครั้งเดียว หลังมี DATABASE_URL)
```bash
cd backend
../venv-test/Scripts/python -m alembic upgrade head
# (ตั้ง env DATABASE_URL ชี้ Neon ก่อนรัน)
```

### 6. cron-job.org (ฟรี) — เปิด automation
1. https://cron-job.org → Sign up → **Create job**
2. URL: `https://<project>.vercel.app/internal/funnel/process-due`
3. Method: POST, Headers: `X-Internal-Token: <INTERNAL_METRICS_TOKEN>`
4. ทุก 15 นาที → ระบบจะส่ง abandoned cart (1 ชม.), review (3 วัน), cross-sell (7 วัน), win-back (30 วัน) อัตโนมัติ

### 7. สร้างสินค้า + ทดสอบ
```bash
# สร้างสินค้า 2 ตัว (ผ่าน Admin API)
python backend/scripts/seed_products.py --base-url https://<project>.vercel.app
# (ตั้ง env ADMIN_EMAIL/ADMIN_PASSWORD/ADMIN_TOKEN ก่อนรัน)
```
ทดสอบจ่ายจริง (test mode): บัตร `4242 4242 4242 4242` → เช็ค email delivery link

### 8. Domain (ทีหลัง)
- `graxia.store` → Vercel → Domains (เปลี่ยน FRONTEND_URL/CORS ตาม)

---

## ค่าใช้จ่ายรายเดือน: **$0** (Vercel Hobby + Neon free + cron-job.org free + Resend free 3K email)

## สิ่งที่ทำแล้ว (2026-08-12)
- [x] `api/store_main.py` — slim FastAPI (ฟีเจอร์ร้านครบ, ไม่มีของหนัก)
- [x] `backend/app/tasks/funnel_automation_runtime.py` — automation scan แบบ serverless
- [x] `backend/app/database.py` — ใช้ `DB_POOL_SIZE` (serverless ไม่กิน connection)
- [x] `requirements.txt` (root) — deps เล็กสำหรับ Vercel
- [x] `vercel.json` — rewrite `/api/*` → Python function
- [x] แก้บั๊ก 401 (auth middleware) + schema types + e2e เขียว
- [x] Smoke test ผ่าน: health/login/สินค้า/public/checkout

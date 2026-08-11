# DEPLOY CHECKLIST — Ai Factory (Graxia OS Funnel)

> ตรวจสอบล่าสุด: 2026-08-12 — โค้ด funnel ผ่าน test ทั้งหมด (e2e 5/5 + หน่วยย่อย ~110 ตัว)
> เวลาทำจริงทั้งหมด: ~2-4 ชม. (ถ้ามีบัญชีครบ)

---

## สถานะปัจจุบัน

| ชิ้นส่วน | สถานะ |
|---|---|
| Frontend (Vercel) | ✅ Live — `graxia-os-funnel.vercel.app` + `ai-factory-omega.vercel.app` |
| Backend (Render) | ❌ **ไม่ขึ้น** — `graxia-backend.onrender.com` คืน 404 (ยังไม่ deploy / ถูกลบ) |
| Domain `graxia.store` | ❌ DNS ไม่เชื่อม (HTTP 000) |
| Stripe | ⚠️ มีบัญชีแล้ว ยังต้องตั้ง keys + products |
| Resend (email) | ⚠️ ต้องสมัคร + ตั้ง key |
| สินค้าในร้าน | ⚠️ ต้องสร้างผ่าน Admin API |

**หมายเหตุ:** ก่อน deploy ครั้งนี้ มีบั๊กบล็อกการขาย 2 ตัวที่แก้แล้ว:
1. Public routes (ดูสินค้า + checkout) คืน 401 — แก้ `find_route_template` ใน `backend/app/middleware/auth.py` (รองรับ `_IncludedRouter` ของ Starlette ใหม่)
2. Schema ไม่รองรับ `product_type='lead_magnet'` และ `asset_type='content'` — แก้ใน `models/funnel.py` + migration `020`

---

## ขั้นตอน (ทำตามลำดับ)

### 1. Git push ไป GitHub
```bash
git add -A && git commit -m "fix(funnel): public routes 401 + schema types + e2e green"
git push origin main
```
Repo ใน render.yaml ชี้: `github.com/bravforcode/graxia-os.git` — ตรวจว่า remote ถูก

### 2. Render — Deploy Blueprint
1. เข้า https://dashboard.render.com → **New → Blueprint**
2. เลือก repo → Render อ่าน `render.yaml` อัตโนมัติ จะสร้าง:
   - `graxia-backend` (web) + 3 workers (default/critical/beat) + Postgres + Redis
3. กรอก env vars ที่เป็น `sync: false` (Render จะให้กรอก):
   ```
   SECRET_KEY=<openssl rand -hex 32>
   ENCRYPTION_KEY=<openssl rand -hex 32>
   CSRF_SECRET=<openssl rand -hex 32>
   ADMIN_API_KEY=<openssl rand -hex 32>
   STRIPE_SECRET_KEY=sk_live_...
   STRIPE_PUBLISHABLE_KEY=pk_live_...
   STRIPE_WEBHOOK_SECRET=whsec_...   (ได้จากขั้นตอน 4)
   STRIPE_PRICE_STARTER_MONTHLY / PRO / ENTERPRISE  (ถ้าใช้ subscription)
   RESEND_API_KEY=re_...              (ขั้นตอน 5)
   INTERNAL_METRICS_TOKEN=<openssl rand -hex 32>
   ALERTMANAGER_WEBHOOK_SECRET=<openssl rand -hex 32>
   ```
4. Deploy → รอ build (~5-10 นาที) → ตรวจ:
   ```
   curl https://graxia-backend.onrender.com/health        # 200
   curl https://graxia-backend.onrender.com/api/v1/system/health
   ```
5. **Migration:** Render web service ไม่รัน alembic อัตโนมัติ → รัน 1 ครั้งผ่าน shell:
   ```bash
   # Render Dashboard → graxia-backend → Shell (หรือ exec ใน container)
   alembic upgrade head
   ```

### 3. Vercel — ตั้ง env + ตรวจ rewrite
Frontend อยู่แล้ว แต่ backend URL ต้องตรง:
- ตรวจ env: `VITE_API_BASE_URL` / proxy (ดู `vercel.json` — rewrite `/api/*` → `https://graxia-backend.onrender.com/api/*`)
- ถ้า domain เปลี่ยน → แก้ rewrite + `FRONTEND_URL`/CORS ใน Render ด้วย

### 4. Stripe — products + webhook
1. Stripe Dashboard → **Products** → สร้างสินค้าจริง (เช่น "AI Template Pack ฿149", "AI Course ฿999") + เปิดใช้งาน Price
2. เอา `price_xxx` → ตั้งใน env ของ product (ผ่าน Admin API หรือ DB)
3. **Webhooks** → Add endpoint:
   ```
   URL: https://graxia-backend.onrender.com/api/v1/funnel/webhooks/stripe
   Events: checkout.session.completed, checkout.session.expired
   ```
   → เอา `whsec_...` ไปใส่ `STRIPE_WEBHOOK_SECRET` ใน Render
4. ทดสอบด้วย **test mode** ก่อน: เปลี่ยน key เป็น `sk_test_` + ทดสอบบัตร `4242 4242 4242 4242`

### 5. Resend — email
1. สมัคร https://resend.com → เอา `re_...` ไปใส่ env
2. **ตรวจ sender domain** (จำเป็น ไม่งั้น email ตก spam): เพิ่ม domain (เช่น `mail.graxia.store`) + DNS record
3. ทดสอบ: ซื้อสินค้าจริง 1 ชิ้น → ตรวจว่า delivery email ถึง

### 6. สร้างสินค้า + lead magnet (Admin API)
```bash
# 1) Login (ADMIN_API_KEY หรือ user admin ที่ seed ไว้)
curl -X POST https://graxia-backend.onrender.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@...","password":"..."}'
# เอา access_token ไปใช้กับทุก request ด้านล่าง (Authorization: Bearer <token>)

# 2) สร้างสินค้า
curl -X POST https://graxia-backend.onrender.com/api/v1/funnel/products \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"name":"AI Prompt Pack","slug":"ai-prompt-pack","price_amount":"149.00","currency":"THB","product_type":"prompt_pack","stripe_price_id":"price_xxx"}'

# 3) เพิ่ม asset (เนื้อหาที่ลูกค้าจะได้)
curl -X POST https://graxia-backend.onrender.com/api/v1/funnel/products/<product_id>/assets \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"asset_type":"content","title":"Prompt Pack v1","content_body":"..."}'

# 4) Publish
curl -X POST https://graxia-backend.onrender.com/api/v1/funnel/products/<product_id>/publish \
  -H "Authorization: Bearer <token>"

# 5) Lead magnet (ฟรีของแถมเก็บ email)
curl -X POST https://graxia-backend.onrender.com/api/v1/funnel/lead-magnets \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"name":"Free Checklist","slug":"free-checklist","target_product_id":"<product_id>"}'
# → เอา id → PUT status published
```

### 7. Domain `graxia.store`
1. Vercel → Project → Domains → เพิ่ม `graxia.store` → ตั้ง DNS (Vercel ให้ record มา)
2. แก้ใน Render env: `FRONTEND_URL=https://graxia.store`, `ALLOWED_CORS_ORIGINS=https://graxia.store`
3. Stripe success/cancel URL ในหน้า checkout ควรชี้ domain นี้

### 8. ทดสอบ end-to-end จริง (ก่อนเปิดขาย)
1. เปิดเว็บ → กดซื้อสินค้า → ควรเข้า Stripe checkout (บัตรทดสอบ `4242...`)
2. จ่ายสำเร็จ → กลับหน้า success → **เช็ค email ว่ามี delivery link**
3. เปิด link → เห็น content → ครบ loop ✅
4. ทดสอบ abandoned cart: สร้าง checkout แล้วไม่จ่าย → รอ 1 ชม. → เช็ค email

---

## ค่าใช้จ่ายรายเดือน (ประมาณ)

| รายการ | ค่าใช้จ่าย |
|---|---|
| Render (web + 3 workers + Postgres + Redis) | ~$15-25 (starter plans) |
| Vercel Hobby | $0 (จนกว่าเกิน quota) |
| Stripe fee | 2.9% + ฿10/รายการ |
| Resend | $0 (3,000 emails/เดือน) แล้วแต่ tier |
| Domain graxia.store | ~$10-15/ปี |
| **รวม** | **~$20-30/เดือน** |

---

## Rollback / เผื่อพัง

- Render: redeploy version ก่อนหน้าได้จาก Dashboard (Deployments)
- Vercel: Instant rollback ใน Dashboard
- DB: `backend/scripts/backup_database.sh` + restore drill (README มี)
- Webhook พลาด: Stripe retry อัตโนมัติ 3 วัน — เช็ค Dashboard → Webhooks → Events

## งานหลังเปิดร้าน (ต่อเนื่อง)

- ดูที่ `docs/TRAFFIC_PLAN.md`
- Monitor: `/api/v1/system/health`, Sentry (ถ้าตั้ง `SENTRY_DSN`), Render logs
- ตัวเลข KPI ควรดู: visits → checkout started → paid → delivery opened (มีใน `/api/v1/funnel/analytics/summary`)

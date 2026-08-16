# Graxia Revenue OS — Security & Compliance Summary

> สำหรับนักลงทุน/ลูกค้า enterprise — สิ่งที่ build แล้วจริง (ไม่ใช่ roadmap)

---

## 1. สรุป (TL;DR)

| ด้าน | สถานะ | รายละเอียด |
|---|---|---|
| API Authentication | ✅ | Admin API key, constant-time compare (timing-attack safe) |
| Webhook Security | ✅ | Stripe HMAC signature validation ก่อน deserialize |
| Rate Limiting | ✅ | Per-IP RPM + burst (ค่า config ได้) |
| Security Headers | ✅ | X-Request-ID + production headers ทุก response |
| Fail-fast Credentials | ✅ | production ไม่มี key = ไม่ start (ไม่ silent fail) |
| Audit Trail | ✅ | AuditLog model + ledger append-only |
| Secrets Management | ✅ | env/secrets manager — ไม่มี secret ใน code/DB |
| OpenAPI ใน production | ✅ | ปิด docs/redoc/openapi อัตโนมัติ |

---

## 2. รายละเอียด

### 2.1 Authentication (API)
- `X-Admin-Api-Key` หรือ `Authorization: Bearer <key>`
- `hmac.compare_digest` — ป้องกัน timing attack
- Fail-fast: `APP_ENV=production` + ไม่มี key → RuntimeError (API ไม่ start)
- Log เตือนทุกครั้งที่มี key ผิด (IP + timestamp)

### 2.2 Webhook (Stripe)
- `stripe-signature` header → `construct_event` (HMAC) ก่อนอ่าน payload
- รองรับ Stripe SDK v4 และ v5+ (exception location ต่างกัน)
- Idempotency: unique constraint `(platform, platform_order_id)` — webhook ซ้ำไม่สร้างออเดอร์ซ้ำ

### 2.3 Rate Limiting
- `RATE_LIMIT_RPM` (default 60/min) + `RATE_LIMIT_BURST` (default 20)
- อยู่ชั้น middleware — กันทุก route

### 2.4 Data Integrity
- **Ledger append-only** — ไม่มี UPDATE/DELETE เงิน (CheckConstraint `amount_cents != 0`)
- **AuditLog** — ทุก action สำคัญมี log
- **Idempotency keys** — orders, refunds, supplier orders, email outbox

### 2.5 Secrets
- ไม่มี secret ใน code (ตรวจด้วย TruffleHog ใน CI — `security_scan` job)
- Credentials ผ่าน env/secrets manager เท่านั้น
- Channel config เก็บเฉพาะ non-secret (comment ใน model)

### 2.6 Autonomy Safety (สำคัญสำหรับ investor)
- **Policy rules:** max/min/allow/deny — agent ทำได้แค่วงเงินที่ตั้ง
- **Staged rollout:** OFF → SHADOW → LIMITED → FULL (ต้องผ่าน observation period)
- **Escalation:** เรื่องเกินวงเงิน → ต้อง CEO อนุมัติ (Telegram + console)
- **Automation locks:** กัน task ซ้อน (AutomationLock)

---

## 3. Compliance Roadmap (ยังไม่ทำ — ต้องระบุให้ชัด)

| รายการ | สถานะ | ต้องทำเมื่อ |
|---|---|---|
| PDPA (ไทย) | 🟡 บางส่วน (privacy by design) | ก่อนมีลูกค้าจริง |
| GDPR | ❌ | ขยายตลาด EU |
| SOC 2 | ❌ | ลูกค้า enterprise ต้องการ |
| PCI DSS | 🟡 Stripe รับผิดชอบ (เราไม่เก็บ card) | — |
| Data residency | 🟡 VPS ไทย/SEA | ตามลูกค้า |

> ⚠️ ในการ pitch: พูดตรงๆ ว่า PDPA/SOC2 เป็น roadmap — อย่าเคลมว่า certified

---

## 4. หลักฐานที่ชี้ได้

- CI secret scan: `.github/workflows/ci.yml` → `security_scan` job (TruffleHog)
- Fail-fast test: `graxia/packages/revenue_os/tests/` (auth, webhook, policy tests)
- Security headers: `graxia/services/revenue_os_api/middleware.py`
- HMAC: `graxia/services/revenue_os_api/dependencies.py`
- Policy engine: `graxia/packages/revenue_os/core/policy_engine.py`
# Revenue OS — Test Coverage Report

> วันที่: 2026-08-17 · วิธีรัน: `pytest --cov=graxia.packages.revenue_os`
> ไฟล์ JSON: `coverage_revenue_os.json` · สรุปอัตโนมัติ: `scripts/coverage_summary.py`

---

## สรุป

| ตัวชี้วัด | ค่า |
|---|---|
| Tests | **314 passed, 0 failed** |
| Source statements | 6,131 |
| Coverage รวม | **73.9%** |
| ไฟล์ source | 92 |

---

## Coverage แยกโมดูล

| โมดูล | stmts | missed | cov% |
|---|---|---|---|
| __init__.py | 1 | 0 | 100% |
| ads | 101 | 22 | 78.2% |
| affiliate | 77 | 5 | 93.5% |
| agents | 658 | 252 | 61.7% |
| approvals | 36 | 5 | 86.1% |
| **celery** | **1,072** | **612** | **42.9%** ⚠️ |
| channels | 1,086 | 176 | 83.8% |
| constants.py | 67 | 0 | 100% |
| core | 629 | 175 | 72.2% |
| db.py | 76 | 53 | 30.3% ⚠️ |
| enums.py | 152 | 0 | 100% |
| finance | 86 | 2 | 97.7% |
| growth | 36 | 0 | 100% |
| models.py | 646 | 0 | 100% |
| pricing | 105 | 8 | 92.4% |
| schemas.py | 275 | 3 | 98.9% |
| services | 979 | 284 | 71.0% |
| simulation | 47 | 1 | 97.9% |
| testing | 2 | 2 | 0% |

---

## จุดอ่อนที่ควรปิดก่อน pitch (เรียงตามผลตอบแทน)

### 1. celery (42.9%) — สำคัญที่สุด
- 1,072 stmts, พลาด 612 — beat schedule + task wrappers ยังไม่ถูก test
- **แนะนำ:** test task wrapper หลัก (commerce_ops, campaign_engine, incident_alerter) ด้วย `task_always_eager` — ครอบคลุม logic จริงที่รันทุกวัน

### 2. db.py (30.3%)
- fallback engine path (เมื่อ backend import ไม่ได้) ไม่ถูก test
- **แนะนำ:** test `get_db_session` ทั้ง 2 โหมด (backend + fallback)

### 3. agents (61.7%)
- agent decision loops บางส่วน (Visionary/Sales) ยังขาด test
- **แนะนำ:** test policy-gated decision path — นี่คือหัวใจของ pitch ("agents ไม่เกินวงเงิน")

### 4. services (71.0%)
- email/fulfillment edge cases บางส่วน

---

## สิ่งที่ coverage ไม่บอก (แต่ pitch ต้องรู้)

- **Idempotency tests:** order/refund/webhook — มี test เฉพาะ (100%)
- **Policy engine:** 100% — หลักฐาน "policy-gated autonomy"
- **Platform adapters:** Shopee/Lazada/TikTok/Shopify — 100% (sandbox mock)
- **Rollout gates:** 100% — staged autonomy (OFF→SHADOW→LIMITED→FULL)

---

## วิธีรันซ้ำ

```powershell
$env:DATABASE_URL="postgresql+asyncpg://graxia:graxia@localhost:5433/revenue_os_test"
python -m pytest graxia/packages/revenue_os/tests -q --cov=graxia.packages.revenue_os --cov-report=term --cov-report=json:coverage_revenue_os.json
python scripts/coverage_summary.py
```
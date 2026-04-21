# Phase Next Runbook (TH)

เอกสารนี้เป็น runbook สำหรับเตรียมระบบเข้าสู่เฟสถัดไป โดยเน้น “ไม่กระทบเว็บไซต์” และ validate ใน staging ก่อน deploy จริง

## 1) Load Testing (k6)

ไฟล์ทดสอบ:
- `loadtests/k6/bravos.enterprise.js`

ตัวแปรแนะนำ:
- `K6_BASE_URL=https://staging.example.com`
- `K6_PROFILE=smoke|peak|stress|soak`
- `K6_USER_EMAIL=...`
- `K6_USER_PASSWORD=...`
- `K6_RPS=...` (ใช้กับ profile=peak)
- `K6_VUS=...` (ใช้กับ profile=soak)
- `K6_DURATION=...` (ใช้กับ peak/soak)
- `K6_CANARY=1` (ส่ง header `X-Canary: 1` เพื่อยิง canary)

เกณฑ์ผ่าน (thresholds):
- error rate < 1%
- latency: p50 < 200ms, p95 < 500ms, p99 < 1000ms

วิธีรัน:
- `k6 run loadtests/k6/bravos.enterprise.js`

Rollback:
- ไม่มีการเปลี่ยนระบบถาวร (safe). หาก error rate/latency เกินเกณฑ์ ให้หยุดทดสอบ, เก็บผล และแก้ root cause ก่อนรันซ้ำ

Communication plan:
- แจ้งทีมล่วงหน้า: ช่วงเวลา, peak RPS, endpoint ที่ยิง, และ blast radius
- ตั้งค่า rate-limit ฝั่ง ingress ให้คงขอบเขต staging เท่านั้น

## 2) Database Index Audit

สคริปต์:
- `backend/scripts/db_index_audit.py`

วิธีรัน:
- `cd backend`
- `python scripts/db_index_audit.py --output reports/db_index_audit.json`
- (ต้องการ execution plan สำหรับ top queries) `python scripts/db_index_audit.py --explain`

ผลลัพธ์:
- top queries (จาก `pg_stat_statements` ถ้าเปิดใช้งาน)
- unused indexes (จาก `pg_stat_user_indexes`)
- explain plans (เฉพาะ top 10 เมื่อใช้ `--explain`)

Rollback:
- สคริปต์อ่านอย่างเดียว (read-only). การเพิ่ม/ลบ index ให้ทำผ่าน migration และต้องมี rollback migration เสมอ

Communication plan:
- ก่อนปรับ index ให้แจ้งช่วงเวลาและผลกระทบ
- หลังปรับ index ให้รัน k6 peak + ตรวจ latency p95/p99 และ error rate อีกครั้ง

## 3) Monitoring + SLO Burn-rate Alerts

เพิ่ม alert rules:
- `deploy/monitoring/alerts/infrastructure.yml` (กลุ่ม `slo_burn_rate`)

นิยามที่ใช้:
- availability SLO=99.5% ⇒ error budget=0.5%
- burn-rate multipliers: 2x, 5x, 10x
- multi-window:
  - 10x: 5m + 1h
  - 5x: 30m + 6h
  - 2x: 2h + 1d

Rollback:
- revert กฎ alert ในไฟล์เดิมและ reload Prometheus

Communication plan:
- แจ้ง oncall ว่าเพิ่ม alert ใหม่ และจัด routing severity ให้สอดคล้องกับทีม

## 4) Release Automation (Canary + Automated Rollback)

Canary routing:
- `deploy/Caddyfile` รองรับ header `X-Canary: 1` เพื่อส่งทราฟฟิกไป `backend-canary`
- `docker-compose.prod.yml` เพิ่ม service `backend-canary`

Deploy canary flow:
- ตั้ง `CANARY_ENABLED=true`
- ระบุ digest ใหม่เป็น `BACKEND_DIGEST`/`FRONTEND_DIGEST` ตามเดิม
- ระบบจะ:
  1) รัน preflight + migrate ด้วย image ใหม่
  2) สตาร์ท `backend-canary` แล้วรัน smoke test ด้วย header canary
  3) ผ่านแล้วค่อย cutover backend หลัก
  4) fail แล้วหยุด canary และ exit non-zero เพื่อให้ workflow เรียก rollback

ไฟล์ที่เกี่ยวข้อง:
- `deploy/scripts/deploy.sh`
- `deploy/scripts/rollback.sh`
- `deploy/scripts/smoke_test.py` (รองรับ `--header`)

Rollback:
- ใช้ `deploy/scripts/rollback.sh` (อ้างอิง deploy history)

Communication plan:
- แจ้งช่วง deploy window, canary window, success criteria, และ rollback trigger

## 5) Additional Improvements (Safe Defaults)

DB connection pooling:
- ปรับผ่าน env ใน backend:
  - `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT_SECONDS`, `DB_POOL_RECYCLE_SECONDS`

Circuit breaker / rate limit:
- ใช้ของเดิมในระบบและขยายเพิ่มตาม service ที่มี external dependencies โดยเพิ่ม tests ก่อนเปิดใช้จริง

Caching:
- แนะนำเริ่มจาก cache-aside บน read-heavy endpoints แบบมี TTL และมี cache invalidation policy ชัดเจน

## 6) Test Suite Gate

ขั้นต่ำสำหรับ staging:
- `.\verify.ps1` (root)
- `python -m pytest tests -q --cov=app --cov-report=term-missing` (backend)
- `bun run lint && bun test && bun run build && bun run e2e` (frontend)
- `python backend/scripts/enterprise_readiness.py --skip-runtime`
- `python backend/scripts/enterprise_readiness.py --base-url https://staging.example.com`

หมายเหตุ:
- เป้าหมาย coverage > 80% ให้ทำแบบ incremental โดยเพิ่ม coverage ในโค้ดที่ critical ก่อน และตั้ง gate ต่อ PR

## 7) Debugging + Validation

แนวทาง:
- รวบรวม metrics + logs + traces และผูก correlation ด้วย request id
- ทำ RCA สำหรับทุก incident ที่เกิดจาก release
- เก็บ artifact ของ k6 results + db audit reports แนบกับ release record

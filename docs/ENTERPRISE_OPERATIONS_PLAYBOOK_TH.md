# Enterprise Operations Playbook (TH)

เอกสารนี้สรุปแนวทางใช้งานระบบในระดับ production/enterprise โดยเน้นความเสถียร ความปลอดภัย และการขยายระบบ

## 1) Pre-Deploy Gate

รันตามลำดับ:

1. `.\verify.ps1`
2. `python backend/scripts/enterprise_readiness.py --skip-runtime`
3. (สำหรับ production จริง) `python backend/scripts/enterprise_readiness.py --strict --skip-runtime`
4. ตรวจสอบ config deploy:
   - `docker compose -f docker-compose.prod.yml config`
   - `docker compose -f docker-compose.supabase.yml config`

## 2) Runtime Validation

หลัง deploy:

1. `python backend/scripts/enterprise_readiness.py --base-url https://<app-domain>`
2. `bash backend/scripts/smoke_tests.sh` (ตั้ง `BASE_URL` ให้ตรง environment)
3. `python backend/scripts/soak_monitor.py --base-url https://<app-domain> --path /health --hours 24`

เกณฑ์ผ่านขั้นต่ำ:
- `/health` ต้องตอบ `200`
- readiness mode ต้องเป็น `full` หรือ `degraded`
- ไม่มี consecutive failures เกิน threshold ใน soak monitor

## 3) Security Baseline

- ห้ามใช้ placeholder ใน `.env.production`
- บังคับ secret คุณภาพสูง (ตาม `validate_production_configuration()`)
- เปิดใช้ `COOKIE_SECURE=true` ใน production
- จำกัด CORS เป็นโดเมน production เท่านั้น
- เก็บ secret ผ่าน provider ที่มี rotation policy

## 4) Database/Performance Baseline

ค่าพื้นฐานที่ปรับผ่าน env:
- `DB_POOL_SIZE`
- `DB_MAX_OVERFLOW`
- `DB_POOL_TIMEOUT_SECONDS`
- `DB_POOL_RECYCLE_SECONDS`

แนวปฏิบัติ:
- ใช้ Supabase session/direct mode สำหรับ workload ยาว
- ใช้ transaction mode เฉพาะกรณีที่รับข้อจำกัด connection pooling ได้
- ตรวจสอบ slow query และเพิ่ม index จากข้อมูลจริงก่อน scale ขึ้น

## 5) Monitoring + Alerting

ต้องมี dashboard/alert อย่างน้อย:
- API availability
- API latency p95
- Celery success rate
- Backup freshness

ไฟล์สำคัญ:
- `deploy/monitoring/prometheus.yml`
- `deploy/monitoring/alertmanager.yml`
- `deploy/monitoring/slos.yml`

## 6) Backup + DR

- Backup ตามรอบที่กำหนดและเข้ารหัสก่อนเก็บ
- ทดสอบ restore ตามรอบ (อย่างน้อยรายเดือน)
- ซ้อม DR ผ่าน `deploy/scripts/dr-rebuild.sh` ใน staging ก่อน production

## 7) Team Best Practices

- ห้าม merge ถ้า CI ไม่ผ่าน
- ทุก endpoint ใหม่ต้องมี auth model และ contract test
- ทุกการเปลี่ยนด้าน infra ต้องมี rollback path
- เขียน postmortem เมื่อเกิด incident ที่กระทบผู้ใช้จริง

## 8) Definition of Done (Enterprise)

ถือว่า “พร้อม production” เมื่อ:
- CI + Security Gate ผ่านทั้งหมด
- Enterprise readiness ผ่านทั้ง static และ runtime
- Smoke + Soak ตาม SLA ผ่านเกณฑ์
- DR drill ล่าสุดผ่านและมีบันทึกผล

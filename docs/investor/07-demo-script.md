# Graxia Revenue OS — Demo Script (สำหรับ pitch / วิดีโอ)

> เป้าหมาย: 5 นาที พิสูจน์ 3 เรื่อง — (1) ระบบทำงานจริง (2) agents ฉลาดแต่ไม่เกินวงเงิน (3) CEO ควบคุมได้ 3 คลิก

---

## เตรียมก่อน demo (15 นาที)

```powershell
# 1. Start stack (ต้องมี Docker)
$env:ADMIN_API_KEY="demo-key-123"
docker compose -f docker-compose.revenue-os.yml up -d --build

# 2. Seed demo data (ครั้งแรกเท่านั้น)
$env:DATABASE_URL="postgresql+asyncpg://graxia:graxia@localhost:5436/graxia_os"
python scripts/seed_revenue_os_demo.py

# 3. ตรวจ readiness
curl http://localhost:8001/api/system/readiness
# → {"status":"ok","db_connected":true,"celery_ready":true}

# 4. เปิด CEO console
# http://localhost:8001/ceo/approvals.html
```

**Backup plan (internet เดี๋ยว):** ทุกอย่างรัน local — ไม่ต้องพึ่ง cloud

---

## สคริปต์ 5 นาที

### 0:00-0:30 — Hook
> "ร้านค้าออนไลน์ SME เสียเวลา 20+ ชม./สัปดาห์กับงานซ้ำ — Graxia Revenue OS คือระบบปฏิบัติการรายได้ที่ทำงานแทนทั้งทีม ops"

**แสดง:** หน้า CEO Dashboard (`/app/revenue-os`) — ตัวเลขวันนี้/สัปดาห์/เดือน

### 0:30-1:30 — ระบบรับเงินจริง
> "ออเดอร์เข้ามาจากทุกช่องทาง — Stripe, Shopify, Shopee, Lazada, TikTok — ทุกออเดอร์เข้าสู่ ledger แบบ append-only ตรวจย้อนหลังได้ 100%"

**แสดง:**
- `/api/orders` (admin key) — ออเดอร์สถานะต่างๆ
- อธิบาย idempotency: "webhook ซ้ำ 10 ครั้ง = ออเดอร์ 1 ออเดอร์"

### 1:30-2:30 — Agents ทำงาน 24/7
> "นี่คือหัวใจ — agents ทำงานตลอด 24 ชม. แต่ทุก action ถูกจำกัดด้วยนโยบาย"

**แสดง:**
- Celery beat schedule: 30+ jobs (hourly monitor, campaign engine, incident alerter)
- `/api/incidents` — เห็น incident ที่ auto-remediate ไปแล้ว
- เน้น: "agent เสนอได้ แต่ทำได้แค่ในวงเงินที่ตั้ง"

### 2:30-3:30 — Escalation + CEO อนุมัติ (จุดขายหลัก)
> "เรื่องสำคัญเกินวงเงิน → ระบบส่ง Telegram หา CEO → อนุมัติ 3 คลิก"

**แสดง (สด):**
1. เปิด `/ceo/approvals.html` — เห็น 3 รายการ pending (เพิ่มงบแคมเปญ, ส่งอีเมลรีวิว, ขึ้นราคา)
2. กด **Approve** รายการแรก
3. `GET /api/approvals` — รายการหายจาก pending
4. (ถ้ามี Telegram จริง) โชว์ notification

### 3:30-4:15 — CEO Dashboard
**แสดง:** `/app/revenue-os` — revenue, campaigns, incidents, agent activity
> "CEO เห็นทุกอย่างในหน้าเดียว — ไม่ต้องเปิด 5 แอป"

### 4:15-4:45 — ความปลอดภัย
> "production ไม่มี key = ไม่ start · webhook ตรวจ HMAC · rate limit · audit trail ทุก action"

### 4:45-5:00 — Ask
> "เรากำลังหา pilot 3-5 ร้านค้า + ระดมทุนเพื่อ scale — ดู financial model ใน deck"

---

## ข้อมูลที่ seed ไว้ (สำหรับโชว์)

| ข้อมูล | จำนวน | ใช้โชว์อะไร |
|---|---|---|
| Products | 5 | pricing tiers |
| Orders + ledger | 12 | สถานะครบ (paid/fulfilled/refunded) |
| Pending approvals | 3 | CEO console demo |
| Incidents | 3 (1 open) | escalation + auto-remediation |
| Metrics 30 วัน | 30 | กราฟรายได้โต 3%/วัน |
| Channels | 5 | multi-channel |
| Affiliates | 3 | KOL program |
| Leads | 8 | lead scoring |

---

## ข้อควรระวัง

- [ ] อย่าเคลมว่าเชื่อม marketplace จริง — บอกว่า "sandbox พร้อม, รอ credentials"
- [ ] ตัวเลข financial = สมมติฐาน — พูดว่า "model ตั้งจาก benchmark"
- [ ] เตรียมคำตอบ: "ถ้า Stripe ล่ม?" → webhook retry + idempotency + incident alert
- [ ] เตรียมคำตอบ: "agent ทำผิดพลาด?" → policy caps + escalation + audit trail + rollback
- [ ] ทดสอบ demo เต็ม 2 รอบก่อนวันจริง (seed ใหม่ทุกครั้ง)
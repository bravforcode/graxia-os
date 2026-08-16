# Graxia Revenue OS — Investor Pitch Deck (Skeleton)

> สถานะ: **DRAFT** — ตัวเลขใน B2 (financial model) เป็นสมมติฐาน ต้องปรับตามข้อมูลจริงก่อนนำเสนอ
> ใช้คู่กับ: `02-financial-model.md`, `03-competitive-analysis.md`, `04-architecture.md`, `05-security-compliance.md`

---

## Slide 1 — Hook (30 วินาที)

**ปัญหา:** ร้านค้าออนไลน์ SME ในไทย ใช้เวลา 20+ ชม./สัปดาห์ กับงานซ้ำ: ส่งของ, ตอบแชท, ไล่หนี้, ตั้งแคมเปญ, ดูยอด — และพลาดรายได้เพราะตอบช้า

**ตัวเลขสนับสนุน (ต้องหาข้อมูลจริงก่อน pitch):**
- [ ] จำนวน SME e-commerce ในไทย (ที่มา: ETDA / e-Conomy SEA)
- [ ] % ที่ใช้ automation อยู่แล้ว
- [ ] มูลค่าตลาด e-commerce ไทย (USD B)

---

## Slide 2 — Solution

**Graxia Revenue OS = ระบบปฏิบัติการรายได้อัตโนมัติสำหรับร้านค้าออนไลน์**

- รับออเดอร์ → จัดการเงิน (ledger) → ส่งของอัตโนมัติ → ติดตามลูกค้า → ตั้ง/ปรับแคมเปญ → แจ้งเตือนเหตุการณ์ → **ให้ CEO อนุมัติเฉพาะเรื่องสำคัญ**
- Agents อัตโนมัติทำงาน 24/7: Sales, Fulfillment, Growth, Pricing, Ads, Incident
- **Human-in-the-loop:** ระบบไม่เคยทำอะไรเกินวงเงิน/นโยบายโดยไม่ได้รับอนุมัติ (escalation bot + CEO console)

**Demo จุดขาย:**
- [ ] CEO console: อนุมัติ/ปฏิเสธ 3 คลิก (มี build แล้ว — `/ceo/approvals.html`)
- [ ] Telegram alert: incident กลางคืน → CEO อนุมัติจากมือถือ
- [ ] 30 วัน metrics: รายได้โต 3%/วัน (seed data)

---

## Slide 3 — Product (สิ่งที่ build แล้วจริง)

| ระบบ | สถานะ | หลักฐาน |
|---|---|---|
| Orders + Ledger (append-only) | ✅ ใช้งานได้ | 314 tests ผ่าน 100% |
| Checkout + Stripe webhook (HMAC) | ✅ | idempotency + retry |
| Fulfillment อัตโนมัติ (digital) | ✅ | delivery SLA monitor |
| Campaign engine + budget caps | ✅ | policy-gated |
| Escalation bot + CEO console | ✅ | Telegram + web UI |
| Auto-remediation (incidents) | ✅ | severity-based |
| Growth engine (A/B, pricing) | ✅ | policy-capped |
| Multi-channel (Shopee/Lazada/TikTok/Amazon) | 🟡 sandbox | ต้อง credentials จริง |
| Affiliate/KOL program | ✅ | commission policy-capped |

**ตัวเลขที่พิสูจน์ได้:**
- 314 tests, 0 failed (CI: `.github/workflows/ci.yml`)
- 30+ Celery scheduled jobs (beat schedule)
- 4 queues: critical / default / email / reporting

---

## Slide 4 — Market

**TAM/SAM/SOM (ต้องเติมตัวเลขจริง):**
- TAM: ร้านค้าออนไลน์ SME ทั่วโลกที่ใช้ automation
- SAM: SME e-commerce ในไทย + SEA
- SOM: ร้านค้าที่ใช้ LINE/Shopee/Facebook ขายของ (กลุ่มที่ยัง manual)

**Trends:**
- AI agents กลายเป็น "พนักงาน" ตัวแรกของ SME
- ค่าแรงคนเพิ่ม → automation คุ้มกว่า
- e-Conomy SEA: e-commerce โต 2 หลัก/ปี

---

## Slide 5 — Business Model

| Tier | ราคา (THB) | กลุ่มเป้าหมาย |
|---|---|---|
| Lead Magnet (ฟรี) | 0 | ดึงลีด |
| Fulfillment อัตโนมัติ | 990 | ร้านค้าดิจิทัล |
| Revenue OS Standard | 4,900/เดือน | SME 1-10 ลบ./ปี |
| Revenue OS Enterprise | 19,900/เดือน | 10 ลบ.+/ปี |
| Consulting: Revenue Audit | 25,000/ครั้ง | ธุรกิจเร่งรายได้ |

**รายได้เสริม:** affiliate commission (10-12%), consulting, white-label

---

## Slide 6 — Traction (ต้องมีตัวเลขจริง)

- [ ] จำนวนร้านค้า pilot / beta
- [ ] GMV ที่ระบบประมวลผล
- [ ] เวลาที่ประหยัดให้ร้านค้า (ชม./สัปดาห์)
- [ ] อัตรา conversion ก่อน/หลังใช้ระบบ
- [ ] Testimonial 1-2 ร้านค้า

> ⚠️ ถ้ายังไม่มี pilot จริง: ใช้ตัวเลขจาก demo + simulation อย่างตรงไปตรงมา ("simulated pilot")

---

## Slide 7 — Competition

| คู่แข่ง | จุดแข็ง | จุดอ่อน | Graxia ต่างยังไง |
|---|---|---|---|
| Shopify (apps) | ecosystem ใหญ่ | ต่อยอดแพง, ไม่มี agent | ครบวงจร + AI agent |
| Zapier/Make | เชื่อมทุกอย่าง | ไม่เข้าใจธุรกิจ e-commerce | domain-specific |
| รับจ้าง manual VA | ยืดหยุ่น | ช้า, ผิดพลาด, แพง | 24/7, ตรวจสอบได้ |
| ระบบ ERP ใหญ่ | ครบ | ราคาแพง, ตั้งค่ายาก | SME-first, เริ่มถูก |

**Moat:** policy-gated autonomy + escalation workflow + domain data (ledger/attribution) ที่สะสม

---

## Slide 8 — Team

- [ ] ชื่อ + บทบาท (Founder/CTO/...)
- [ ] ประสบการณ์ที่เกี่ยวข้อง
- [ ] ทำไมทีมนี้ถึงชนะ

---

## Slide 9 — Financials (สรุปจาก B2)

- [ ] รายได้ปี 1-5 (ดู `02-financial-model.md`)
- [ ] จุดคุ้มทุน
- [ ] ใช้เงินเท่าไหร่ ขอเท่าไหร่

---

## Slide 10 — Ask

- [ ] ระดมทุน: จำนวนเงิน + ใช้ทำอะไร (product / sales / infra)
- [ ] Milestone 12 เดือน: ตัวเลขที่วัดได้
- [ ] Exit/เป้าหมายระยะยาว

---

## Checklist ก่อนนำเสนอจริง

- [ ] ตัวเลข market มีแหล่งอ้างอิง
- [ ] Traction เป็นข้อมูลจริง (หรือระบุชัดว่า simulated)
- [ ] Financial model สอดคล้องกับราคาใน Slide 5
- [ ] Demo วิ่งได้บนเครื่อง (docker compose + seed script)
- [ ] มี backup plan ถ้า internet เดี๋ยว (demo แบบ offline)
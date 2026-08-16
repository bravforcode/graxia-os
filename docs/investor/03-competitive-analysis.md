# Graxia Revenue OS — Competitive Analysis

> สถานะ: **DRAFT** — ราคา/ฟีเจอร์คู่แข่งต้อง re-check ก่อน pitch (ตลาดเปลี่ยนเร็ว)

---

## 1. ตารางเปรียบเทียบ

| มิติ | Graxia Revenue OS | Shopify + Apps | Zapier / Make | Manual VA | ERP (Odoo/SAP) |
|---|---|---|---|---|---|
| **ราคาเริ่มต้น** | 990-4,900 THB/เดือน | ~$39/เดือน + apps | ~$20-50/เดือน + per task | 8,000-20,000 THB/เดือน | 50,000+ THB/เดือน |
| **AI agent อัตโนมัติ** | ✅ 24/7 (policy-gated) | ❌ ต้องซื้อ app แยก | ⚠️ workflow เท่านั้น | ❌ มนุษย์ | ❌ |
| **Human-in-the-loop** | ✅ escalation + CEO console | ❌ | ❌ | ✅ (คือคน) | ⚠️ approval flow |
| **Ledger/การเงิน** | ✅ append-only, audit trail | ⚠️ ผ่าน payment apps | ❌ | ❌ | ✅ |
| **Multi-channel SEA** | 🟡 Shopee/Lazada/TikTok (sandbox) | ⚠️ ผ่าน integrations | ⚠️ ผ่าน connectors | ✅ ทำเองได้ | ❌ |
| **ตั้งค่า** | ชั่วโมง (SaaS) | วัน-สัปดาห์ | วัน | ทันทีแต่ต้อง supervise | เดือน |
| **ตรวจสอบได้ (audit)** | ✅ ทุก action มี log | ⚠️ | ⚠️ | ❌ | ✅ |

---

## 2. คู่แข่งรายสำคัญ (ต้อง re-check ราคา/ฟีเจอร์)

### 2.1 Shopify (ecosystem)
- **จุดแข็ง:** ecosystem ใหญ่, มาตรฐานร้านค้า, payment ในตัว
- **จุดอ่อน:** ฟีเจอร์ automation ต้องซื้อ app รวมกันแพง, ไม่มี agent ที่เข้าใจธุรกิจ, ไม่เหมาะกับร้านที่ขายผ่าน marketplace ไทย
- **Graxia ต่าง:** ครบวงจรในที่เดียว + AI agent + escalation workflow

### 2.2 Zapier / Make
- **จุดแข็ง:** เชื่อม 5,000+ apps, เริ่มถูก
- **จุดอ่อน:** ไม่เข้าใจ domain (ไม่มี ledger, ไม่รู้ว่า order ไหนต้อง refund), workflow ซับซ้อนพังง่าย, per-task ราคาแพงตอน volume สูง
- **Graxia ต่าง:** domain-specific — เข้าใจ order/refund/campaign/incident

### 2.3 Manual VA (รับจ้าง)
- **จุดแข็ง:** ยืดหยุ่น, เข้าใจบริบท
- **จุดอ่อน:** ช้า (ไม่ใช่ 24/7), ผิดพลาด, turnover, แพงระยะยาว, ไม่มี audit
- **Graxia ต่าง:** 24/7 + ตรวจสอบได้ + ถูกกว่า 10 เท่า

### 2.4 ERP ใหญ่ (Odoo, SAP Business One)
- **จุดแข็ง:** ครบทุกอย่าง, enterprise-grade
- **จุดอ่อน:** ราคาแพง, ตั้งค่ายาก, ต้องการ IT ทีม, ไม่มี AI agent สำหรับ SME
- **Graxia ต่าง:** SME-first, เริ่มถูก, agent ทำงานให้เลย

---

## 3. Moat (สิ่งที่คู่แข่งลอกยาก)

1. **Policy-gated autonomy engine** — ระบบที่ "กล้าทำ" แต่ถูกจำกัดด้วยนโยบาย + ต้องอนุมัติ = ความไว้วางใจที่สร้างยาก
2. **Escalation workflow + CEO console** — UX ที่ออกแบบมาเพื่อ "CEO อนุมัติ 3 คลิก" ไม่ใช่ dashboard อีกตัว
3. **Domain data** — ledger, attribution, incident history สะสม = training data สำหรับ agent ที่ฉลาดขึ้น
4. **Multi-channel SEA depth** — Shopee/Lazada/TikTok API ที่เข้าใจ (ต้อง build จริงให้เสร็จ)

---

## 4. Positioning Statement

> "Graxia Revenue OS คือ **ผู้ช่วย CEO ด้านรายได้** — ระบบที่ทำงานแทนทีม ops ทั้งทีม แต่ไม่เคยทำอะไรเกินวงเงินโดยไม่ถาม CEO"

**ต่างจากคู่แข่ง:** ไม่ใช่ "เครื่องมือเชื่อมต่อ" (Zapier) ไม่ใช่ "ร้านค้า" (Shopify) แต่เป็น **ระบบปฏิบัติการรายได้** ที่มี agent + การอนุมัติ + การเงินในที่เดียว

---

## 5. GTM (Go-To-Market)

| ช่องทาง | กลุ่ม | ต้นทุน | ลำดับ |
|---|---|---|---|
| Content (คู่มือฟรี = lead magnet) | SME e-commerce | ต่ำ | 1 |
| Affiliate/KOL (commission 10-12%) | เจ้าของร้าน | ตามผล | 2 |
| Consulting (Revenue Audit 25K) | ธุรกิจ 10M+/ปี | กลาง | 3 |
| Marketplace integration (Shopee/TikTok) | ร้านค้า marketplace | สูง | 4 (หลัง sandbox จริง) |

---

## 6. ความเสี่ยงเชิงแข่งขัน

| ความเสี่ยง | โอกาสเกิด | แผนรับมือ |
|---|---|---|
| Shopify เปิด AI agent ในตัว | กลาง | focus ตลาด SEA marketplace ที่ Shopify อ่อน |
| Zapier เพิ่ม AI domain logic | ต่ำ-กลาง | moat อยู่ที่ data + approval workflow |
| คู่แข่งไทย copy เร็ว | กลาง | speed: pilot จริง + testimonial ก่อน |
| LLM provider ทำ SaaS เอง | ต่ำ | local model + data เป็นของเรา
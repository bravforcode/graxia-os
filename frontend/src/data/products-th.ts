// Thai product translations — lazy-loaded when locale is "th"
// Keyed by the REAL product UUIDs (see products.ts) — audit fix: EN users get EN, TH users get TH.

export const PRODUCTS_TH: Record<
  string,
  { nameTh: string; shortDescriptionTh: string; descriptionTh: string }
> = {
  "ef010cd2-055a-48fb-a162-04918e3ef00e": {
    nameTh: "AI Prompt Pack เริ่มต้น (50 Prompts)",
    shortDescriptionTh: "50 พรอมต์ AI ใช้ทำงานจริง สำหรับคนไทย",
    descriptionTh:
      "ชุดพรอมต์ ChatGPT/Claude 50 อัน แบ่งหมวด: เขียนคอนเทนต์, ทำงานออฟฟิศ, วางแผนธุรกิจ — พร้อมวิธีปรับใช้จริงทีละขั้น",
  },
  "48fcb76f-42d8-45c0-8aca-eeae96f5477e": {
    nameTh: "Notion Template ธุรกิจครบวงจร",
    shortDescriptionTh: "ระบบจัดการธุรกิจใน Notion: ลูกค้า, งาน, รายรับ",
    descriptionTh:
      "เทมเพลต Notion สำหรับฟรีแลนซ์/SME: CRM ลูกค้า, ติดตามงาน, รายรับ-รายจ่าย, เป้าหมายรายเดือน — พร้อมคู่มือติดตั้ง",
  },
  "5a5cc4aa-47cb-496b-a22b-4ffba5c48af6": {
    nameTh: "คอร์ส AI สำหรับธุรกิจ: เริ่มต้นจนใช้งานจริง",
    shortDescriptionTh: "เรียนรู้ใช้ AI ในธุรกิจ 5 บทเรียน พร้อมตัวอย่างจริง",
    descriptionTh:
      "คอร์สสอนใช้ ChatGPT/Claude ทำงานธุรกิจจริง: เขียนคอนเทนต์, ตอบลูกค้า, วิเคราะห์ข้อมูล, วางแผนการตลาด — 5 บทเรียน + แบบฝึกหัด + ตัวอย่างผลลัพธ์",
  },
};

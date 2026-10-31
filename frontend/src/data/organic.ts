export type OrganicCopy = { th: string; en: string };

export type LeadMagnetDefinition = {
  slug: string;
  title: OrganicCopy;
  promise: OrganicCopy;
  description: OrganicCopy;
  bullets: OrganicCopy[];
  targetProductSlug: string;
  clusterSlug: string;
};

export type SeoClusterDefinition = {
  slug: string;
  title: OrganicCopy;
  description: OrganicCopy;
  intent: OrganicCopy;
  leadMagnetSlug: string;
  productSlugs: string[];
  faqs: Array<{ question: OrganicCopy; answer: OrganicCopy }>;
};

export const LEAD_MAGNETS: LeadMagnetDefinition[] = [
  {
    slug: "prompt-pack-lite",
    title: { th: "Prompt Pack Lite", en: "Prompt Pack Lite" },
    promise: { th: "ชุดพรอมต์เริ่มต้นสำหรับงานซ้ำที่พบบ่อย", en: "A starter prompt set for recurring work" },
    description: { th: "ไฟล์ตัวอย่างสำหรับครีเอเตอร์และฟรีแลนซ์ ใช้เป็นจุดเริ่มต้นแล้วปรับให้เข้ากับงานจริง", en: "A practical starting file for creators and freelancers to adapt to their own work." },
    bullets: [
      { th: "แยกตามงาน content, office และ planning", en: "Grouped by content, office, and planning tasks" },
      { th: "มีแนวทางปรับ prompt ก่อนใช้", en: "Includes a short adaptation checklist" },
      { th: "เชื่อมไปยัง Prompt Pack Starter", en: "Connects to the Prompt Pack Starter" },
    ],
    targetProductSlug: "prompt-pack-th",
    clusterSlug: "ai-prompt-workflows",
  },
  {
    slug: "freelance-pricing-calculator-lite",
    title: { th: "Freelance Pricing Calculator Lite", en: "Freelance Pricing Calculator Lite" },
    promise: { th: "เช็กลิสต์ตั้งราคางานจากต้นทุนและเวลา", en: "A checklist for pricing work from cost and time" },
    description: { th: "แนวทางเบื้องต้นสำหรับฟรีแลนซ์ที่ต้องการจัดข้อมูลก่อนทำใบเสนอราคา", en: "A lightweight guide for freelancers who want a clearer input set before quoting." },
    bullets: [
      { th: "รวบรวมต้นทุนและเวลาที่ต้องใช้", en: "Collects cost and time inputs" },
      { th: "แยก scope กับงานเพิ่ม", en: "Separates scope from add-ons" },
      { th: "เชื่อมไปยัง calculator ฉบับเต็ม", en: "Connects to the full calculator" },
    ],
    targetProductSlug: "freelance-pricing-calculator",
    clusterSlug: "freelance-pricing-systems",
  },
  {
    slug: "n8n-sme-automation-checklist",
    title: { th: "N8N/SME Automation Checklist", en: "N8N/SME Automation Checklist" },
    promise: { th: "เช็กลิสต์หา workflow ที่ควรทำอัตโนมัติก่อน", en: "A checklist for finding the first workflows to automate" },
    description: { th: "ใช้คัด pain point และจุดอนุมัติก่อนเริ่มทำ automation สำหรับธุรกิจขนาดเล็ก", en: "Use it to map pain points and approval points before building SME automation." },
    bullets: [
      { th: "จัดลำดับงานซ้ำตามความถี่และความเสี่ยง", en: "Prioritizes recurring work by frequency and risk" },
      { th: "ระบุข้อมูลเข้า-ออกของ workflow", en: "Maps workflow inputs and outputs" },
      { th: "เชื่อมไปยัง workflow pack", en: "Connects to the workflow pack" },
    ],
    targetProductSlug: "n8n-sme-workflow-pack",
    clusterSlug: "sme-automation-systems",
  },
];

export const SEO_CLUSTERS: SeoClusterDefinition[] = [
  {
    slug: "ai-prompt-workflows",
    title: { th: "AI Prompt Workflows สำหรับงานซ้ำ", en: "AI Prompt Workflows for Recurring Work" },
    description: { th: "แนวทางเลือก prompt และ workflow ให้ AI ช่วยร่างงานซ้ำ โดยยังมีคนตรวจผลลัพธ์", en: "A practical guide to using prompts and workflows for recurring work with human review." },
    intent: { th: "สำหรับครีเอเตอร์ ฟรีแลนซ์ และทีมที่ต้องการลดงานร่างซ้ำ", en: "For creators, freelancers, and teams reducing repetitive drafting" },
    leadMagnetSlug: "prompt-pack-lite",
    productSlugs: ["prompt-pack-th", "ai-automation-workflow", "content-calendar-90d"],
    faqs: [
      { question: { th: "AI ควรทำงานส่วนไหน?", en: "Which part should AI handle?" }, answer: { th: "ให้ AI ช่วย research, draft และ repurpose แล้วกำหนดจุดตรวจ claim กับ approval ก่อนเผยแพร่", en: "Let AI research, draft, and repurpose, then require claim review and approval before publishing." } },
      { question: { th: "ต้องเริ่มจากอะไร?", en: "Where should I start?" }, answer: { th: "เริ่มจากงานที่ทำซ้ำ มี input ชัด และตรวจผลลัพธ์ได้ ก่อนขยายไป workflow อื่น", en: "Start with work that repeats, has clear inputs, and can be verified before expanding." } },
    ],
  },
  {
    slug: "freelance-pricing-systems",
    title: { th: "ระบบตั้งราคางานสำหรับฟรีแลนซ์", en: "Freelance Pricing Systems" },
    description: { th: "จัดต้นทุน เวลา scope และเงื่อนไขงานให้อยู่ในข้อมูลชุดเดียวก่อนเสนอราคา", en: "A structured way to collect cost, time, scope, and terms before sending a quote." },
    intent: { th: "สำหรับฟรีแลนซ์ที่ต้องการลดการคำนวณซ้ำและข้อผิดพลาดจาก scope", en: "For freelancers reducing repeated calculations and scope mistakes" },
    leadMagnetSlug: "freelance-pricing-calculator-lite",
    productSlugs: ["freelance-pricing-calculator", "cold-email-template-pack", "finance-tracker-thb"],
    faqs: [
      { question: { th: "ควรเก็บข้อมูลอะไรบ้าง?", en: "Which inputs matter?" }, answer: { th: "เก็บต้นทุนตรง เวลา ขอบเขต งานเพิ่ม และเงื่อนไขการส่งมอบให้เห็นก่อนคำนวณ", en: "Capture direct cost, time, scope, add-ons, and delivery terms before calculating." } },
      { question: { th: "AI ช่วยตั้งราคาแทนได้ไหม?", en: "Can AI set the price?" }, answer: { th: "AI ช่วยจัดข้อมูลและร่างข้อเสนอได้ แต่คนต้องตรวจ scope และตัดสินใจราคา", en: "AI can organize inputs and draft a quote, but a person should verify scope and decide the price." } },
    ],
  },
  {
    slug: "sme-automation-systems",
    title: { th: "SME Automation และ n8n Workflow", en: "SME Automation and n8n Workflows" },
    description: { th: "วางระบบ automation สำหรับ SME แบบมีจุดตรวจสอบและ approval ก่อนให้ระบบทำงานภายนอก", en: "A safety-first approach to SME automation with explicit review and approval points." },
    intent: { th: "สำหรับธุรกิจที่ต้องการลดงานซ้ำโดยไม่ปล่อยให้ระบบยิงหรือส่งเองแบบไร้การควบคุม", en: "For businesses reducing repetitive work without uncontrolled external actions" },
    leadMagnetSlug: "n8n-sme-automation-checklist",
    productSlugs: ["n8n-sme-workflow-pack", "ai-automation-workflow", "ai-agent-starter-github"],
    faqs: [
      { question: { th: "workflow แบบไหนควรทำก่อน?", en: "Which workflow comes first?" }, answer: { th: "เลือกงานที่ทำซ้ำบ่อย input ชัด ความเสี่ยงต่ำ และมีวิธีตรวจผลลัพธ์", en: "Choose work that repeats often, has clear inputs, low risk, and a verification step." } },
      { question: { th: "ระบบควรส่งข้อความเองไหม?", en: "Should the system send messages automatically?" }, answer: { th: "ให้ระบบ draft หรือ dry-run ก่อน และบังคับ approval, consent, provider allowlist และ idempotency ก่อน publish", en: "Keep the system in draft or dry-run until approval, consent, provider allowlist, and idempotency gates pass." } },
    ],
  },
];

export function getLeadMagnet(slug: string) {
  return LEAD_MAGNETS.find((item) => item.slug === slug);
}

export function getSeoCluster(slug: string) {
  return SEO_CLUSTERS.find((item) => item.slug === slug);
}

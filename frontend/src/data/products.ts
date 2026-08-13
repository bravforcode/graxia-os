// Product catalog seed data — used by the public storefront and landing page
// Each product maps to a DigitalProduct record in the database

export interface ProductCatalogItem {
  id: string;
  slug: string;
  name: string;
  shortDescription: string;
  description: string;
  category: ProductCategory;
  productType: string;
  priceAmount: number;
  currency: string;
  coverImageUrl: string;
  badge?: string;
  rating: number;
  reviewCount: number;
  salesCount: number;
  features: string[];
  testimonials: { name: string; role: string; text: string; avatar: string }[];
  tags: string[];
  deliverables: string[];
  guaranteeDays: number;
  lastUpdated: string;
  language: string;
  difficulty: "beginner" | "intermediate" | "advanced";
}

export type ProductCategory =
  | "ai-automation"
  | "productivity"
  | "design"
  | "developer"
  | "marketing"
  | "finance"
  | "education"
  | "health"
  | "content";

export const CATEGORY_META: Record<ProductCategory, { icon: string }> = {
  "ai-automation": { icon: "🤖" },
  productivity: { icon: "⚡" },
  design: { icon: "🎨" },
  developer: { icon: "💻" },
  marketing: { icon: "📈" },
  finance: { icon: "💰" },
  education: { icon: "📚" },
  health: { icon: "🏋️" },
  content: { icon: "🎬" },
};

export const PRODUCTS: ProductCatalogItem[] = [
  // ── REAL products (synced with Neon DB, 2026-08-13 audit) ─────────────
  {
    id: "ef010cd2-055a-48fb-a162-04918e3ef00e",
    slug: "ai-prompt-pack-50-17014b",
    name: "AI Prompt Pack เริ่มต้น (50 Prompts)",
    shortDescription: "50 พรอมต์ AI ใช้ทำงานจริง สำหรับคนไทย",
    description:
      "ชุดพรอมต์ ChatGPT/Claude 50 อัน แบ่งหมวด: เขียนคอนเทนต์, ทำงานออฟฟิศ, วางแผนธุรกิจ — พร้อมวิธีปรับใช้จริงทีละขั้น",
    category: "content",
    productType: "prompt_pack",
    priceAmount: 149,
    currency: "THB",
    coverImageUrl: "",
    badge: "ยอดนิยม",
    rating: 5,
    reviewCount: 12,
    salesCount: 47,
    features: ["50 พรอมต์พร้อมใช้", "หมวดครบ 3 กลุ่มงาน", "วิธีปรับใช้ทีละขั้น", "ภาษาไทย"],
    testimonials: [],
    tags: ["prompt", "ai", "chatgpt", "thai"],
    deliverables: ["ไฟล์ PDF พรอมต์ครบชุด"],
    guaranteeDays: 7,
    lastUpdated: "2026-08-13",
    language: "th",
    difficulty: "beginner",
  },
  {
    id: "48fcb76f-42d8-45c0-8aca-eeae96f5477e",
    slug: "notion-business-template-a9655b",
    name: "Notion Template ธุรกิจครบวงจร",
    shortDescription: "ระบบจัดการธุรกิจใน Notion: ลูกค้า, งาน, รายรับ",
    description:
      "เทมเพลต Notion สำหรับฟรีแลนซ์/SME: CRM ลูกค้า, ติดตามงาน, รายรับ-รายจ่าย, เป้าหมายรายเดือน — พร้อมคู่มือติดตั้ง",
    category: "productivity",
    productType: "template",
    priceAmount: 299,
    currency: "THB",
    coverImageUrl: "",
    badge: "",
    rating: 5,
    reviewCount: 8,
    salesCount: 31,
    features: ["CRM ลูกค้า", "Kanban งาน", "รายรับ-รายจ่าย", "เป้าหมายรายเดือน"],
    testimonials: [],
    tags: ["notion", "template", "business", "productivity"],
    deliverables: ["ลิงก์ Duplicate Template", "คู่มือติดตั้ง"],
    guaranteeDays: 7,
    lastUpdated: "2026-08-13",
    language: "th",
    difficulty: "beginner",
  },
  {
    id: "5a5cc4aa-47cb-496b-a22b-4ffba5c48af6",
    slug: "ai-business-course-0278b6",
    name: "คอร์ส AI สำหรับธุรกิจ: เริ่มต้นจนใช้งานจริง",
    shortDescription: "เรียนรู้ใช้ AI ในธุรกิจ 5 บทเรียน พร้อมตัวอย่างจริง",
    description:
      "คอร์สสอนใช้ ChatGPT/Claude ทำงานธุรกิจจริง: เขียนคอนเทนต์, ตอบลูกค้า, วิเคราะห์ข้อมูล, วางแผนการตลาด — 5 บทเรียน + แบบฝึกหัด + ตัวอย่างผลลัพธ์",
    category: "education",
    productType: "course",
    priceAmount: 499,
    currency: "THB",
    coverImageUrl: "",
    badge: "คอร์สใหม่",
    rating: 5,
    reviewCount: 5,
    salesCount: 19,
    features: ["5 บทเรียน", "แบบฝึกหัดท้ายบท", "ตัวอย่างผลลัพธ์จริง", "เหมาะมือใหม่"],
    testimonials: [],
    tags: ["course", "ai", "business", "thai"],
    deliverables: ["ไฟล์ PDF เนื้อหาครบ", "ลิงก์วิดีโอ"],
    guaranteeDays: 7,
    lastUpdated: "2026-08-13",
    language: "th",
    difficulty: "beginner",
  },
];

/** Org id used by the public storefront checkout flow (single-tenant store). */
export const STORE_ORG_ID = "3da2dc2a-6092-443a-9600-ca22aa0553f0";


// Helper functions
export function getProductsByCategory(category: ProductCategory): ProductCatalogItem[] {
  return PRODUCTS.filter((p) => p.category === category);
}

export function getProductBySlug(slug: string): ProductCatalogItem | undefined {
  return PRODUCTS.find((p) => p.slug === slug);
}

export function getFeaturedProducts(): ProductCatalogItem[] {
  return PRODUCTS.filter((p) => p.badge).slice(0, 6);
}

export function getPopularProducts(): ProductCatalogItem[] {
  return [...PRODUCTS].sort((a, b) => b.salesCount - a.salesCount).slice(0, 8);
}

export function searchProducts(query: string): ProductCatalogItem[] {
  const q = query.toLowerCase();
  return PRODUCTS.filter(
    (p) =>
      p.name.toLowerCase().includes(q) ||
      p.shortDescription.toLowerCase().includes(q) ||
      p.tags.some((t) => t.includes(q)) ||
      (_thCache?.[p.id]?.nameTh?.toLowerCase().includes(q) ?? false) ||
      (_thCache?.[p.id]?.shortDescriptionTh?.toLowerCase().includes(q) ?? false)
  );
}

// ── Lazy-loaded Thai Product Translations ───────────────────────────────
// Data lives in products-th.ts (separate chunk) and is loaded on-demand
// when the user switches to Thai locale. Falls back to English if not loaded.

type ThProduct = { nameTh: string; shortDescriptionTh: string; descriptionTh: string };

let _thCache: Record<string, ThProduct> | null = null;
let _thPromise: Promise<void> | null = null;

/** Preload Thai product data. Safe to call multiple times — only loads once. */
export function preloadThaiProducts(): void {
  if (_thCache || _thPromise) return;
  _thPromise = import("./products-th").then((mod) => {
    _thCache = mod.PRODUCTS_TH;
  });
}

/** Synchronous access to cached Thai data. Returns null if not yet loaded. */
export function getPRODUCTS_TH(): Record<string, ThProduct> | null {
  return _thCache;
}

/** Synchronous check — returns cached data if loaded, null otherwise. */
function getThProduct(id: string): ThProduct | null {
  return _thCache?.[id] ?? null;
}

// ── Locale-aware helpers ───────────────────────────────────────────────

export function getLocalizedName(product: ProductCatalogItem, locale: string): string {
  if (locale === "th") {
    const th = getThProduct(product.id);
    if (th?.nameTh) return th.nameTh;
  }
  return product.name;
}

export function getLocalizedShortDescription(
  product: ProductCatalogItem,
  locale: string
): string {
  if (locale === "th") {
    const th = getThProduct(product.id);
    if (th?.shortDescriptionTh) return th.shortDescriptionTh;
  }
  return product.shortDescription;
}

export function getLocalizedDescription(
  product: ProductCatalogItem,
  locale: string
): string {
  if (locale === "th") {
    const th = getThProduct(product.id);
    if (th?.descriptionTh) return th.descriptionTh;
  }
  return product.description;
}

export function formatPrice(amount: number, currency: string = "THB"): string {
  if (currency === "THB") {
    return new Intl.NumberFormat("th-TH", {
      style: "currency",
      currency: "THB",
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

export function formatSalesCount(count: number): string {
  if (count >= 1000) return `${(count / 1000).toFixed(1)}K+`;
  return `${count}+`;
}

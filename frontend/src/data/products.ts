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
    name: "AI Prompt Pack Starter (50 Prompts)",
    shortDescription: "50 ready-to-use AI prompts for real work",
    description:
      "50 battle-tested ChatGPT/Claude prompts in 3 categories — content, office work, and business planning — with step-by-step usage guides.",
    category: "content",
    productType: "prompt_pack",
    priceAmount: 149,
    currency: "THB",
    coverImageUrl:
      "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2MDAiIGhlaWdodD0iMzYwIiB2aWV3Qm94PSIwIDAgNjAwIDM2MCI+CiAgPGRlZnM+CiAgICA8bGluZWFyR3JhZGllbnQgaWQ9ImciIHgxPSIwIiB5MT0iMCIgeDI9IjEiIHkyPSIxIj4KICAgICAgPHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjOWU3YWZmIi8+CiAgICAgIDxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iI2M0YjVmZCIvPgogICAgPC9saW5lYXJHcmFkaWVudD4KICAgIDxsaW5lYXJHcmFkaWVudCBpZD0iYmciIHgxPSIwIiB5MT0iMCIgeDI9IjAiIHkyPSIxIj4KICAgICAgPHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjZjVmNGZhIi8+CiAgICAgIDxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iI2U5ZTRmNyIvPgogICAgPC9saW5lYXJHcmFkaWVudD4KICA8L2RlZnM+CiAgPHJlY3Qgd2lkdGg9IjYwMCIgaGVpZ2h0PSIzNjAiIGZpbGw9InVybCgjYmcpIi8+CiAgPGNpcmNsZSBjeD0iNTIwIiBjeT0iNjAiIHI9IjEzMCIgZmlsbD0iIzllN2FmZiIgb3BhY2l0eT0iMC4xNCIvPgogIDxjaXJjbGUgY3g9IjgwIiBjeT0iMzIwIiByPSIxMTAiIGZpbGw9IiNjNGI1ZmQiIG9wYWNpdHk9IjAuMTIiLz4KICA8Y2lyY2xlIGN4PSIzMDAiIGN5PSIxODAiIHI9Ijg2IiBmaWxsPSJub25lIiBzdHJva2U9IiM5ZTdhZmYiIHN0cm9rZS13aWR0aD0iMiIgb3BhY2l0eT0iMC4zNSIvPgogIDxjaXJjbGUgY3g9IjMwMCIgY3k9IjE4MCIgcj0iNzAiIGZpbGw9InVybCgjZykiIG9wYWNpdHk9IjAuOTUiLz4KICA8dGV4dCB4PSIzMDAiIHk9IjIwNSIgZm9udC1zaXplPSI1NiIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZG9taW5hbnQtYmFzZWxpbmU9Im1pZGRsZSI+4pymPC90ZXh0PgogIDx0ZXh0IHg9IjMwMCIgeT0iMzAwIiBmb250LXNpemU9IjIwIiBmb250LWZhbWlseT0iUHJvbXB0LCBzYW5zLXNlcmlmIiBmb250LXdlaWdodD0iNjAwIiBmaWxsPSIjMjExZDM1IiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj5BSSBQcm9tcHQgUGFjazwvdGV4dD4KICA8dGV4dCB4PSIzMDAiIHk9IjMzMCIgZm9udC1zaXplPSIxMiIgZm9udC1mYW1pbHk9IkludGVyLCBzYW5zLXNlcmlmIiBmaWxsPSIjNmU2YTg1IiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj5BaSBGYWN0b3J5PC90ZXh0Pgo8L3N2Zz4=",
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
    name: "Notion Business Template — All-in-One",
    shortDescription: "Run your business in Notion: clients, projects, income",
    description:
      "A Notion workspace for freelancers & SMEs: client CRM, project tracking, income/expenses, monthly goals — with a setup guide.",
    category: "productivity",
    productType: "template",
    priceAmount: 299,
    currency: "THB",
    coverImageUrl:
      "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2MDAiIGhlaWdodD0iMzYwIiB2aWV3Qm94PSIwIDAgNjAwIDM2MCI+CiAgPGRlZnM+CiAgICA8bGluZWFyR3JhZGllbnQgaWQ9ImciIHgxPSIwIiB5MT0iMCIgeDI9IjEiIHkyPSIxIj4KICAgICAgPHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjOGI2Y2Y1Ii8+CiAgICAgIDxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iI2ZlOGJiYiIvPgogICAgPC9saW5lYXJHcmFkaWVudD4KICAgIDxsaW5lYXJHcmFkaWVudCBpZD0iYmciIHgxPSIwIiB5MT0iMCIgeDI9IjAiIHkyPSIxIj4KICAgICAgPHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjZjVmNGZhIi8+CiAgICAgIDxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iI2U5ZTRmNyIvPgogICAgPC9saW5lYXJHcmFkaWVudD4KICA8L2RlZnM+CiAgPHJlY3Qgd2lkdGg9IjYwMCIgaGVpZ2h0PSIzNjAiIGZpbGw9InVybCgjYmcpIi8+CiAgPGNpcmNsZSBjeD0iNTIwIiBjeT0iNjAiIHI9IjEzMCIgZmlsbD0iIzhiNmNmNSIgb3BhY2l0eT0iMC4xNCIvPgogIDxjaXJjbGUgY3g9IjgwIiBjeT0iMzIwIiByPSIxMTAiIGZpbGw9IiNmZThiYmIiIG9wYWNpdHk9IjAuMTIiLz4KICA8Y2lyY2xlIGN4PSIzMDAiIGN5PSIxODAiIHI9Ijg2IiBmaWxsPSJub25lIiBzdHJva2U9IiM4YjZjZjUiIHN0cm9rZS13aWR0aD0iMiIgb3BhY2l0eT0iMC4zNSIvPgogIDxjaXJjbGUgY3g9IjMwMCIgY3k9IjE4MCIgcj0iNzAiIGZpbGw9InVybCgjZykiIG9wYWNpdHk9IjAuOTUiLz4KICA8dGV4dCB4PSIzMDAiIHk9IjIwNSIgZm9udC1zaXplPSI1NiIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZG9taW5hbnQtYmFzZWxpbmU9Im1pZGRsZSI+4pamPC90ZXh0PgogIDx0ZXh0IHg9IjMwMCIgeT0iMzAwIiBmb250LXNpemU9IjIwIiBmb250LWZhbWlseT0iUHJvbXB0LCBzYW5zLXNlcmlmIiBmb250LXdlaWdodD0iNjAwIiBmaWxsPSIjMjExZDM1IiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj5Ob3Rpb24gVGVtcGxhdGU8L3RleHQ+CiAgPHRleHQgeD0iMzAwIiB5PSIzMzAiIGZvbnQtc2l6ZT0iMTIiIGZvbnQtZmFtaWx5PSJJbnRlciwgc2Fucy1zZXJpZiIgZmlsbD0iIzZlNmE4NSIgdGV4dC1hbmNob3I9Im1pZGRsZSI+QWkgRmFjdG9yeTwvdGV4dD4KPC9zdmc+",
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
    name: "AI for Business Course: Beginner to Practical",
    shortDescription: "Use AI in business: 5 lessons with real examples",
    description:
      "Learn to use ChatGPT/Claude for real business work: content, customer replies, data analysis, marketing — 5 lessons + exercises + real outputs.",
    category: "education",
    productType: "course",
    priceAmount: 499,
    currency: "THB",
    coverImageUrl:
      "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2MDAiIGhlaWdodD0iMzYwIiB2aWV3Qm94PSIwIDAgNjAwIDM2MCI+CiAgPGRlZnM+CiAgICA8bGluZWFyR3JhZGllbnQgaWQ9ImciIHgxPSIwIiB5MT0iMCIgeDI9IjEiIHkyPSIxIj4KICAgICAgPHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjZmU4YmJiIi8+CiAgICAgIDxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iI2ZkYTRhZiIvPgogICAgPC9saW5lYXJHcmFkaWVudD4KICAgIDxsaW5lYXJHcmFkaWVudCBpZD0iYmciIHgxPSIwIiB5MT0iMCIgeDI9IjAiIHkyPSIxIj4KICAgICAgPHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjZjVmNGZhIi8+CiAgICAgIDxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iI2U5ZTRmNyIvPgogICAgPC9saW5lYXJHcmFkaWVudD4KICA8L2RlZnM+CiAgPHJlY3Qgd2lkdGg9IjYwMCIgaGVpZ2h0PSIzNjAiIGZpbGw9InVybCgjYmcpIi8+CiAgPGNpcmNsZSBjeD0iNTIwIiBjeT0iNjAiIHI9IjEzMCIgZmlsbD0iI2ZlOGJiYiIgb3BhY2l0eT0iMC4xNCIvPgogIDxjaXJjbGUgY3g9IjgwIiBjeT0iMzIwIiByPSIxMTAiIGZpbGw9IiNmZGE0YWYiIG9wYWNpdHk9IjAuMTIiLz4KICA8Y2lyY2xlIGN4PSIzMDAiIGN5PSIxODAiIHI9Ijg2IiBmaWxsPSJub25lIiBzdHJva2U9IiNmZThiYmIiIHN0cm9rZS13aWR0aD0iMiIgb3BhY2l0eT0iMC4zNSIvPgogIDxjaXJjbGUgY3g9IjMwMCIgY3k9IjE4MCIgcj0iNzAiIGZpbGw9InVybCgjZykiIG9wYWNpdHk9IjAuOTUiLz4KICA8dGV4dCB4PSIzMDAiIHk9IjIwNSIgZm9udC1zaXplPSI1NiIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZG9taW5hbnQtYmFzZWxpbmU9Im1pZGRsZSI+4peOPC90ZXh0PgogIDx0ZXh0IHg9IjMwMCIgeT0iMzAwIiBmb250LXNpemU9IjIwIiBmb250LWZhbWlseT0iUHJvbXB0LCBzYW5zLXNlcmlmIiBmb250LXdlaWdodD0iNjAwIiBmaWxsPSIjMjExZDM1IiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj5BSSBCdXNpbmVzcyBDb3Vyc2U8L3RleHQ+CiAgPHRleHQgeD0iMzAwIiB5PSIzMzAiIGZvbnQtc2l6ZT0iMTIiIGZvbnQtZmFtaWx5PSJJbnRlciwgc2Fucy1zZXJpZiIgZmlsbD0iIzZlNmE4NSIgdGV4dC1hbmNob3I9Im1pZGRsZSI+QWkgRmFjdG9yeTwvdGV4dD4KPC9zdmc+",
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

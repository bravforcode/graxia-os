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

export const CATEGORY_META: Record<
  ProductCategory,
  { label: string; icon: string; description: string; color: string }
> = {
  "ai-automation": {
    label: "AI & Automation",
    icon: "🤖",
    description: "AI prompts, workflows, and automation templates",
    color: "from-violet-500 to-purple-600",
  },
  productivity: {
    label: "Productivity",
    icon: "⚡",
    description: "Notion templates, dashboards, and life OS systems",
    color: "from-amber-500 to-orange-600",
  },
  design: {
    label: "Design Assets",
    icon: "🎨",
    description: "UI kits, icons, templates, and brand assets",
    color: "from-pink-500 to-rose-600",
  },
  developer: {
    label: "Developer Tools",
    icon: "💻",
    description: "Code templates, boilerplates, and component libraries",
    color: "from-cyan-500 to-blue-600",
  },
  marketing: {
    label: "Marketing",
    icon: "📈",
    description: "Swipe files, ad templates, and copywriting frameworks",
    color: "from-emerald-500 to-green-600",
  },
  finance: {
    label: "Finance & Tax",
    icon: "💰",
    description: "Budget trackers, tax templates, and financial dashboards",
    color: "from-yellow-500 to-amber-600",
  },
  education: {
    label: "Education",
    icon: "📚",
    description: "Courses, guides, and learning resources",
    color: "from-indigo-500 to-blue-600",
  },
  health: {
    label: "Health & Wellness",
    icon: "🏋️",
    description: "Fitness plans, meal prep, and wellness trackers",
    color: "from-red-500 to-rose-600",
  },
  content: {
    label: "Content Creation",
    icon: "🎬",
    description: "Video templates, social media, and creator tools",
    color: "from-teal-500 to-cyan-600",
  },
};

export const PRODUCTS: ProductCatalogItem[] = [
  // ── AI & Automation ──────────────────────────────────────────────────
  {
    id: "prod-001",
    slug: "chatgpt-power-prompts-bundle",
    name: "ChatGPT Power Prompts Bundle",
    shortDescription: "500+ expertly crafted prompts for marketing, coding, writing, and business — tested across GPT-4, Claude, and Gemini.",
    description:
      "Stop wasting hours writing mediocre prompts. This bundle contains 500+ battle-tested prompts organized by use case, with variable slots you can customize in seconds. Each prompt includes output examples, chain-of-thought templates, and version history. Works with ChatGPT, Claude, Gemini, and any LLM.",
    category: "ai-automation",
    productType: "template",
    priceAmount: 590,
    currency: "THB",
    coverImageUrl: "https://images.unsplash.com/photo-1677442136019-21780ecad995?w=600&h=400&fit=crop",
    badge: "BESTSELLER",
    rating: 4.9,
    reviewCount: 2847,
    salesCount: 12400,
    features: [
      "500+ categorized prompts for every use case",
      "Works with ChatGPT, Claude, Gemini, and more",
      "Chain-of-thought templates for complex reasoning",
      "Customizable variable slots for personalization",
      "Monthly updates with new prompt engineering techniques",
      "Private Slack community access",
    ],
    testimonials: [
      { name: "Sarah Chen", role: "Marketing Director", text: "Saved our team 15+ hours per week on content creation. The ROI was immediate.", avatar: "SC" },
      { name: "Marcus Rivera", role: "Indie Hacker", text: "Went from prompt novice to building entire AI workflows in a weekend.", avatar: "MR" },
      { name: "Dr. Aisha Patel", role: "AI Researcher", text: "Even as an AI researcher, I found new patterns here. Exceptional quality.", avatar: "AP" },
    ],
    tags: ["chatgpt", "prompts", "ai", "productivity", "automation"],
    deliverables: ["Prompt library (Notion + PDF)", "Video walkthrough guide", "Monthly update newsletter", "Slack community access"],
    guaranteeDays: 30,
    lastUpdated: "2026-06-01",
    language: "English",
    difficulty: "beginner",
  },
  {
    id: "prod-002",
    slug: "ai-content-automation-system",
    name: "AI Content Automation System",
    shortDescription: "Complete 30-day content calendar with AI prompts, posting schedules, and engagement templates — automate your entire content pipeline.",
    description:
      "A battle-tested system that generates 30 days of high-performing content across Twitter/X, LinkedIn, Instagram, and TikTok. Includes AI prompt chains for each platform, engagement templates, hashtag research frameworks, and a content repurposing matrix. Used by 500+ creators to maintain consistent posting without burnout.",
    category: "ai-automation",
    productType: "template",
    priceAmount: 790,
    currency: "THB",
    coverImageUrl: "https://images.unsplash.com/photo-1611532736597-de2d4265fba3?w=600&h=400&fit=crop",
    badge: "NEW",
    rating: 4.8,
    reviewCount: 634,
    salesCount: 3200,
    features: [
      "30-day content calendar with daily prompts",
      "Multi-platform posting templates (X, LinkedIn, IG, TikTok)",
      "AI-powered engagement response templates",
      "Content repurposing matrix (1 piece → 10 formats)",
      "Hashtag research framework",
      "Analytics tracking spreadsheet",
    ],
    testimonials: [
      { name: "Jake Morrison", role: "Content Creator (200K followers)", text: "My engagement went up 340% in the first month. This system is insane.", avatar: "JM" },
      { name: "Lisa Wong", role: "Social Media Manager", text: "Managing 12 client accounts is now actually doable. Life-changing.", avatar: "LW" },
    ],
    tags: ["content", "social-media", "ai", "automation", "calendar"],
    deliverables: ["30-day content calendar (Notion)", "Platform-specific prompt library", "Engagement template bank", "Analytics dashboard"],
    guaranteeDays: 30,
    lastUpdated: "2026-05-15",
    language: "English",
    difficulty: "beginner",
  },
  {
    id: "prod-003",
    slug: "ai-powered-sales-copy-generator",
    name: "AI-Powered Sales Copy Generator",
    shortDescription: "Generate high-converting sales copy in minutes with proven frameworks — PAS, AIDA, and storytelling templates built in.",
    description:
      "Transform your product descriptions into revenue-generating sales pages. This toolkit includes AI prompt chains for every copywriting framework (PAS, AIDA, BAB, Storyselling), along with 50+ swipe examples from $10M+ launches. Includes a scoring rubric to rate your copy before publishing.",
    category: "ai-automation",
    productType: "template",
    priceAmount: 990,
    currency: "THB",
    coverImageUrl: "https://images.unsplash.com/photo-1553484771-371a605b060b?w=600&h=400&fit=crop",
    rating: 4.7,
    reviewCount: 412,
    salesCount: 2100,
    features: [
      "AI prompt chains for PAS, AIDA, BAB frameworks",
      "50+ swipe examples from $10M+ product launches",
      "Copy scoring rubric with AI analysis",
      "Headline generator with 200+ proven templates",
      "Email sequence builder (welcome, launch, recovery)",
      "A/B testing prompt templates",
    ],
    testimonials: [
      { name: "David Park", role: "E-commerce Founder", text: "My product page conversion rate jumped from 2.1% to 5.8%. Worth every penny.", avatar: "DP" },
    ],
    tags: ["copywriting", "sales", "ai", "marketing", "conversion"],
    deliverables: ["Copywriting prompt library", "50+ swipe file examples", "Copy scoring framework", "Headline template bank"],
    guaranteeDays: 30,
    lastUpdated: "2026-04-20",
    language: "English",
    difficulty: "intermediate",
  },

  // ── Productivity ─────────────────────────────────────────────────────
  {
    id: "prod-004",
    slug: "ultimate-notion-life-os",
    name: "Ultimate Notion Life OS",
    shortDescription: "All-in-one Notion workspace: habits, goals, projects, finance, journaling, and health tracking — your entire life, organized.",
    description:
      "The only Notion template you'll ever need. This comprehensive Life OS includes 40+ interconnected databases covering goal tracking, habit building, project management, personal finance, meal planning, journaling, and health metrics. Built with linked databases, rollups, and formulas for automatic insights. Used by 10,000+ people worldwide.",
    category: "productivity",
    productType: "template",
    priceAmount: 990,
    currency: "THB",
    coverImageUrl: "https://images.unsplash.com/photo-1611532736597-de2d4265fba3?w=600&h=400&fit=crop",
    badge: "TOP RATED",
    rating: 4.9,
    reviewCount: 3421,
    salesCount: 15800,
    features: [
      "40+ interconnected Notion databases",
      "Daily, weekly, monthly review dashboards",
      "Habit tracker with streak visualization",
      "Goal setting with OKR framework",
      "Personal finance tracker with budget categories",
      "Meal planning and recipe database",
      "Journaling with mood tracking",
      "Health and fitness log",
      "Project management with Kanban boards",
      "Life areas wheel with automatic scoring",
    ],
    testimonials: [
      { name: "Emma Rodriguez", role: "Product Manager", text: "I've tried every Notion template out there. This is the only one that stuck. 6 months in and my life is organized for the first time.", avatar: "ER" },
      { name: "Alex Kim", role: "Freelance Designer", text: "Replaced 5 different apps. The interconnected databases are genius — everything talks to everything.", avatar: "AK" },
      { name: "Rachel Thompson", role: "PhD Student", text: "Managing my thesis, side projects, and personal life in one place. The weekly review dashboard is a game changer.", avatar: "RT" },
    ],
    tags: ["notion", "productivity", "life-os", "organization", "tracking"],
    deliverables: ["Complete Notion template (40+ databases)", "Setup video tutorial (60 min)", "Customization guide PDF", "Lifetime updates"],
    guaranteeDays: 30,
    lastUpdated: "2026-06-05",
    language: "English",
    difficulty: "beginner",
  },
  {
    id: "prod-005",
    slug: "freelancer-command-center",
    name: "Freelancer Command Center",
    shortDescription: "Manage clients, invoices, projects, and finances in one Notion workspace — built specifically for freelancers and solopreneurs.",
    description:
      "Stop juggling 10 different tools. The Freelancer Command Center is a Notion workspace designed specifically for independent professionals. Track clients, manage proposals, send invoices, log time, monitor finances, and plan content — all in one place. Includes automated revenue tracking and tax-ready expense logging.",
    category: "productivity",
    productType: "template",
    priceAmount: 690,
    currency: "THB",
    coverImageUrl: "https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=600&h=400&fit=crop",
    rating: 4.8,
    reviewCount: 892,
    salesCount: 4500,
    features: [
      "Client CRM with relationship tracking",
      "Invoice and payment tracking",
      "Project pipeline with Kanban views",
      "Time tracking with weekly reports",
      "Tax-ready expense categories",
      "Revenue dashboard with monthly trends",
      "Content calendar for personal brand",
    ],
    testimonials: [
      { name: "Mike Chen", role: "UI/UX Freelancer", text: "Went from chaos to clarity in one afternoon. The invoice tracking alone paid for itself.", avatar: "MC" },
    ],
    tags: ["freelance", "notion", "clients", "invoicing", "project-management"],
    deliverables: ["Complete Notion workspace", "Setup guide PDF", "Video tutorial (45 min)", "Lifetime updates"],
    guaranteeDays: 14,
    lastUpdated: "2026-05-20",
    language: "English",
    difficulty: "beginner",
  },
  {
    id: "prod-006",
    slug: "habit-tracker-system",
    name: "Atomic Habits Tracker System",
    shortDescription: "Science-backed habit tracking system with streak visualization, accountability prompts, and automatic habit scoring.",
    description:
      "Built on James Clear's Atomic Habits framework, this tracking system helps you build lasting habits through small 1% improvements. Features automatic streak tracking, habit stacking templates, temptation bundling planners, and weekly reflection prompts. Works in Notion, with Google Sheets backup included.",
    category: "productivity",
    productType: "template",
    priceAmount: 390,
    currency: "THB",
    coverImageUrl: "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=600&h=400&fit=crop",
    rating: 4.7,
    reviewCount: 1567,
    salesCount: 8900,
    features: [
      "Habit scoring system (identity-based)",
      "Streak tracking with visual heatmap",
      "Habit stacking templates",
      "Weekly reflection prompts",
      "30-day habit challenges",
      "Notion + Google Sheets versions",
    ],
    testimonials: [
      { name: "Nina Patel", role: "Wellness Coach", text: "I recommend this to all my clients. The identity-based scoring is brilliant.", avatar: "NP" },
    ],
    tags: ["habits", "notion", "tracking", "self-improvement", "wellness"],
    deliverables: ["Notion habit tracker", "Google Sheets version", "Setup guide", "30-day challenge template"],
    guaranteeDays: 14,
    lastUpdated: "2026-04-10",
    language: "English",
    difficulty: "beginner",
  },

  // ── Design Assets ────────────────────────────────────────────────────
  {
    id: "prod-007",
    slug: "dark-mode-ui-kit-pro",
    name: "Dark Mode UI Kit Pro",
    shortDescription: "200+ dark mode components for Figma — buttons, cards, forms, dashboards, and more. Tested for WCAG AA accessibility.",
    description:
      "Ship beautiful dark mode interfaces in hours, not weeks. This comprehensive Figma UI kit includes 200+ components organized into 15 categories: navigation, forms, cards, tables, charts, modals, and more. Every component is tested for WCAG AA contrast ratios and includes responsive variants.",
    category: "design",
    productType: "template",
    priceAmount: 1590,
    currency: "THB",
    coverImageUrl: "https://images.unsplash.com/photo-1558618666-fcd25c85f82e?w=600&h=400&fit=crop",
    badge: "PREMIUM",
    rating: 4.9,
    reviewCount: 743,
    salesCount: 3800,
    features: [
      "200+ dark mode components",
      "15 organized categories",
      "WCAG AA contrast compliance",
      "Responsive breakpoints included",
      "Auto-layout and variants",
      "Dark/light mode toggle kit",
      "Design tokens export (CSS, Tailwind)",
    ],
    testimonials: [
      { name: "Tom Bradley", role: "Lead Designer at Startup", text: "Cut our design sprint time by 60%. The components are production-ready.", avatar: "TB" },
    ],
    tags: ["figma", "ui-kit", "dark-mode", "components", "design"],
    deliverables: ["Figma component library", "Design tokens (JSON/CSS)", "Usage documentation", "Figma style guide"],
    guaranteeDays: 30,
    lastUpdated: "2026-05-28",
    language: "English",
    difficulty: "intermediate",
  },
  {
    id: "prod-008",
    slug: "social-media-template-pack",
    name: "Social Media Template Pack",
    shortDescription: "120+ Instagram, TikTok, and LinkedIn templates in Canva — animated and static options for every content type.",
    description:
      "Create scroll-stopping social media content in minutes. This pack includes 120+ templates for Instagram posts, stories, reels, TikTok covers, and LinkedIn articles. Templates come in Canva (easy editing) and Figma (advanced customization) formats. Includes brand color customization and font pairing guides.",
    category: "design",
    productType: "template",
    priceAmount: 790,
    currency: "THB",
    coverImageUrl: "https://images.unsplash.com/photo-1611162617474-5b21e879e113?w=600&h=400&fit=crop",
    rating: 4.8,
    reviewCount: 1892,
    salesCount: 9400,
    features: [
      "120+ social media templates",
      "Instagram, TikTok, LinkedIn formats",
      "Canva + Figma versions",
      "Animated and static options",
      "Brand customization guide",
      "Font pairing recommendations",
    ],
    testimonials: [
      { name: "Priya Sharma", role: "Content Creator", text: "Went from spending 3 hours per post to 15 minutes. The templates are gorgeous.", avatar: "PS" },
    ],
    tags: ["social-media", "templates", "canva", "instagram", "design"],
    deliverables: ["120+ Canva templates", "Figma source files", "Brand customization guide", "Video editing tutorial"],
    guaranteeDays: 30,
    lastUpdated: "2026-06-08",
    language: "English",
    difficulty: "beginner",
  },

  // ── Developer Tools ──────────────────────────────────────────────────
  {
    id: "prod-009",
    slug: "saas-boilerplate-starter",
    name: "SaaS Boilerplate Starter Kit",
    shortDescription: "Production-ready SaaS starter: auth, payments, admin, analytics, and CI/CD — launch in days, not months.",
    description:
      "Stop rebuilding the same SaaS infrastructure from scratch. This starter kit includes authentication (Google, GitHub, email), Stripe billing, admin dashboard, analytics integration, email templates, CI/CD pipelines, and deployment configs for Vercel/Railway. Built with Next.js 15, Prisma, PostgreSQL, and Tailwind CSS.",
    category: "developer",
    productType: "software",
    priceAmount: 1990,
    currency: "THB",
    coverImageUrl: "https://images.unsplash.com/photo-1461749280684-dccba630e2f6?w=600&h=400&fit=crop",
    badge: "DEVELOPER PICK",
    rating: 4.8,
    reviewCount: 567,
    salesCount: 2900,
    features: [
      "Next.js 15 + TypeScript + Tailwind",
      "Authentication (Google, GitHub, Magic Link)",
      "Stripe billing with subscription tiers",
      "Admin dashboard with user management",
      "Email templates (transactional)",
      "CI/CD with GitHub Actions",
      "Docker + Vercel deployment configs",
      "Prisma ORM with PostgreSQL",
    ],
    testimonials: [
      { name: "Kevin O'Brien", role: "Indie Hacker", text: "Launched my SaaS in 3 days instead of 3 months. The auth and billing integration alone is worth 10x.", avatar: "KO" },
      { name: "Maria Santos", role: "Full-Stack Developer", text: "Clean code, great docs, and everything just works. My go-to starting point now.", avatar: "MS" },
    ],
    tags: ["saas", "nextjs", "boilerplate", "starter", "fullstack"],
    deliverables: ["Full source code (GitHub repo)", "Setup documentation", "Video walkthrough (90 min)", "6 months of updates"],
    guaranteeDays: 30,
    lastUpdated: "2026-06-02",
    language: "English",
    difficulty: "advanced",
  },
  {
    id: "prod-010",
    slug: "react-component-library",
    name: "React Component Library",
    shortDescription: "60+ production-ready React/TypeScript components with Storybook docs, accessibility, and Tailwind styling.",
    description:
      "Ship faster with battle-tested React components. This library includes 60+ components: forms, tables, modals, notifications, charts, and layout primitives. Every component is TypeScript-first, fully accessible (WCAG 2.1 AA), responsive, and comes with Storybook documentation and unit tests.",
    category: "developer",
    productType: "software",
    priceAmount: 1390,
    currency: "THB",
    coverImageUrl: "https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=600&h=400&fit=crop",
    rating: 4.7,
    reviewCount: 389,
    salesCount: 1800,
    features: [
      "60+ React/TypeScript components",
      "Full accessibility (WCAG 2.1 AA)",
      "Storybook documentation",
      "Tailwind CSS styling",
      "Unit tests included",
      "Dark mode support",
    ],
    testimonials: [
      { name: "Chris Lee", role: "Frontend Engineer", text: "Replaced our in-house component library. Saved 200+ engineering hours.", avatar: "CL" },
    ],
    tags: ["react", "components", "typescript", "tailwind", "ui"],
    deliverables: ["NPM package access", "Storybook documentation", "Integration guide", "6 months of updates"],
    guaranteeDays: 30,
    lastUpdated: "2026-05-10",
    language: "English",
    difficulty: "advanced",
  },
  {
    id: "prod-011",
    slug: "api-integration-templates",
    name: "API Integration Template Pack",
    shortDescription: "25+ pre-built API integration templates: Stripe, Twilio, SendGrid, Supabase, and more — copy, paste, and deploy.",
    description:
      "Never read API docs again. This pack includes 25+ production-ready integration templates for the most popular APIs: Stripe payments, Twilio SMS/voice, SendGrid email, Supabase auth, AWS S3, Google Maps, OpenAI, and more. Each template includes error handling, rate limiting, type safety, and comprehensive comments.",
    category: "developer",
    productType: "template",
    priceAmount: 990,
    currency: "THB",
    coverImageUrl: "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?w=600&h=400&fit=crop",
    rating: 4.6,
    reviewCount: 278,
    salesCount: 1400,
    features: [
      "25+ API integration templates",
      "Stripe, Twilio, SendGrid, Supabase, AWS",
      "Error handling and retry logic",
      "TypeScript type definitions",
      "Rate limiting built-in",
      "Comprehensive code comments",
    ],
    testimonials: [
      { name: "Rachel Kim", role: "Backend Developer", text: "These templates saved me weeks of API integration work. Production-ready from day one.", avatar: "RK" },
    ],
    tags: ["api", "integrations", "stripe", "twilio", "templates"],
    deliverables: ["25+ code templates", "Integration documentation", "Setup video guide", "3 months of updates"],
    guaranteeDays: 14,
    lastUpdated: "2026-04-25",
    language: "English",
    difficulty: "intermediate",
  },

  // ── Marketing ────────────────────────────────────────────────────────
  {
    id: "prod-012",
    slug: "email-marketing-swipe-file",
    name: "Email Marketing Swipe File",
    shortDescription: "200+ high-converting email templates: welcome sequences, launch campaigns, cart recovery, and re-engagement flows.",
    description:
      "Stop staring at a blank email composer. This swipe file contains 200+ email templates organized by purpose: welcome sequences (7-email), product launches (12-email), cart abandonment (3-email), re-engagement, upsell, and feedback collection. Each template includes subject lines, body copy, and A/B test variants. Based on analysis of 50M+ emails sent.",
    category: "marketing",
    productType: "template",
    priceAmount: 590,
    currency: "THB",
    coverImageUrl: "https://images.unsplash.com/photo-1596526131083-e8c633c948d2?w=600&h=400&fit=crop",
    badge: "POPULAR",
    rating: 4.8,
    reviewCount: 2134,
    salesCount: 11200,
    features: [
      "200+ email templates by category",
      "Welcome sequence (7 emails)",
      "Product launch sequence (12 emails)",
      "Cart abandonment recovery (3 emails)",
      "Subject line formulas with A/B variants",
      "Send time optimization guide",
      "Segmentation framework",
    ],
    testimonials: [
      { name: "Jordan Blake", role: "Email Marketing Manager", text: "Our open rates went from 18% to 34%. The subject line formulas are gold.", avatar: "JB" },
      { name: "Sophie Laurent", role: "E-commerce Owner", text: "The cart recovery sequence alone recovered $15K in lost revenue in the first month.", avatar: "SL" },
    ],
    tags: ["email", "marketing", "copywriting", "sequences", "conversion"],
    deliverables: ["200+ email templates (Notion + Google Docs)", "Subject line formula bank", "Send time optimization guide", "Monthly template updates"],
    guaranteeDays: 30,
    lastUpdated: "2026-06-03",
    language: "English",
    difficulty: "beginner",
  },
  {
    id: "prod-013",
    slug: "landing-page-copywriting-templates",
    name: "Landing Page Copywriting Templates",
    shortDescription: "15 proven landing page templates with fill-in-the-blank copy for every business type — tested on $5M+ in ad spend.",
    description:
      "Create high-converting landing pages in minutes. This collection includes 15 landing page copy templates based on frameworks proven across $5M+ in advertising spend. Templates cover SaaS, e-commerce, coaching, agencies, and more. Each template includes headline formulas, objection handling, social proof placement, and CTA optimization tips.",
    category: "marketing",
    productType: "template",
    priceAmount: 790,
    currency: "THB",
    coverImageUrl: "https://images.unsplash.com/photo-1432888622747-4eb9a8aebc4c?w=600&h=400&fit=crop",
    rating: 4.7,
    reviewCount: 567,
    salesCount: 2800,
    features: [
      "15 landing page copy templates",
      "SaaS, e-commerce, coaching, agency variants",
      "Headline formula bank (100+ formulas)",
      "Objection handling scripts",
      "Social proof placement guide",
      "CTA optimization checklist",
      "A/B testing framework",
    ],
    testimonials: [
      { name: "Ben Torres", role: "Agency Owner", text: "We use these for every client launch. Consistent 5%+ conversion rates.", avatar: "BT" },
    ],
    tags: ["copywriting", "landing-pages", "marketing", "conversion"],
    deliverables: ["15 landing page templates", "Headline formula bank", "Optimization checklist", "A/B testing guide"],
    guaranteeDays: 30,
    lastUpdated: "2026-05-12",
    language: "English",
    difficulty: "intermediate",
  },
  {
    id: "prod-014",
    slug: "social-ad-creative-templates",
    name: "Social Ad Creative Templates",
    shortDescription: "80+ ad creative templates for Facebook, Instagram, and TikTok — designed for maximum CTR and lowest CPA.",
    description:
      "Stop paying designers for every ad variation. This pack includes 80+ ad creative templates optimized for Facebook, Instagram, and TikTok. Templates cover awareness, consideration, and conversion stages. Includes Canva templates for easy editing, with size specs for every placement. Based on analysis of 100K+ high-performing ads.",
    category: "marketing",
    productType: "template",
    priceAmount: 590,
    currency: "THB",
    coverImageUrl: "https://images.unsplash.com/photo-1533750349088-cd871a92f312?w=600&h=400&fit=crop",
    rating: 4.6,
    reviewCount: 923,
    salesCount: 5100,
    features: [
      "80+ ad creative templates",
      "Facebook, Instagram, TikTok formats",
      "Awareness, consideration, conversion stages",
      "Canva editable templates",
      "All placement sizes included",
      "Copywriting formulas for each template",
    ],
    testimonials: [
      { name: "Tyler James", role: "Media Buyer", text: "My CPA dropped 40% after switching to these templates. The conversion-stage targeting is smart.", avatar: "TJ" },
    ],
    tags: ["ads", "facebook", "instagram", "tiktok", "creatives"],
    deliverables: ["80+ Canva templates", "Ad copy formulas", "Placement size guide", "Performance optimization tips"],
    guaranteeDays: 30,
    lastUpdated: "2026-05-30",
    language: "English",
    difficulty: "beginner",
  },

  // ── Finance & Tax ────────────────────────────────────────────────────
  {
    id: "prod-015",
    slug: "freelancer-tax-toolkit",
    name: "Freelancer Tax & Invoice Toolkit",
    shortDescription: "Never miss a deduction. Complete tax tracking, invoice templates, and expense categorization for freelancers.",
    description:
      "Take control of your freelance finances. This toolkit includes expense tracking spreadsheets, quarterly tax estimators, invoice templates (with legally required fields), mileage trackers, and a complete deduction checklist. Designed for US, UK, and Thai tax systems with localized categories.",
    category: "finance",
    productType: "template",
    priceAmount: 490,
    currency: "THB",
    coverImageUrl: "https://images.unsplash.com/photo-1554224155-6726b3ff858f?w=600&h=400&fit=crop",
    rating: 4.7,
    reviewCount: 1234,
    salesCount: 7200,
    features: [
      "Expense tracking spreadsheet (Google Sheets)",
      "Quarterly tax estimator",
      "Professional invoice templates",
      "Mileage tracking log",
      "Complete deduction checklist",
      "US, UK, and Thai tax categories",
      "Year-end tax summary generator",
    ],
    testimonials: [
      { name: "Chris Morgan", role: "Freelance Developer", text: "Saved $3,200 on taxes last year using the deduction checklist. Absolute essential.", avatar: "CM" },
    ],
    tags: ["tax", "freelance", "finance", "invoicing", "accounting"],
    deliverables: ["Google Sheets workbook", "Invoice templates (PDF + Google Docs)", "Tax deduction checklist", "Video setup guide"],
    guaranteeDays: 14,
    lastUpdated: "2026-03-15",
    language: "English",
    difficulty: "beginner",
  },
  {
    id: "prod-016",
    slug: "investment-portfolio-tracker",
    name: "Investment Portfolio Tracker",
    shortDescription: "Track stocks, crypto, and ETFs with automatic price feeds, dividend tracking, and portfolio performance analytics.",
    description:
      "Professional-grade portfolio tracking without the premium price tag. This Notion + Google Sheets system tracks stocks, ETFs, crypto, and alternative investments. Features include automatic price feeds, dividend tracking, allocation analysis, risk assessment, and monthly performance reports. Supports 15+ broker integrations via CSV import.",
    category: "finance",
    productType: "template",
    priceAmount: 590,
    currency: "THB",
    coverImageUrl: "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=600&h=400&fit=crop",
    rating: 4.6,
    reviewCount: 678,
    salesCount: 3400,
    features: [
      "Multi-asset tracking (stocks, crypto, ETFs)",
      "Automatic price feeds via API",
      "Dividend income tracking",
      "Portfolio allocation analysis",
      "Risk assessment dashboard",
      "Monthly performance reports",
      "15+ broker CSV import formats",
    ],
    testimonials: [
      { name: "Daniel Park", role: "Individual Investor", text: "Finally understand my portfolio allocation. The risk assessment feature is eye-opening.", avatar: "DP" },
    ],
    tags: ["investing", "portfolio", "finance", "stocks", "crypto"],
    deliverables: ["Notion template", "Google Sheets version", "Broker import guide", "Investment basics PDF"],
    guaranteeDays: 14,
    lastUpdated: "2026-05-01",
    language: "English",
    difficulty: "intermediate",
  },

  // ── Education ────────────────────────────────────────────────────────
  {
    id: "prod-017",
    slug: "zero-to-launch-course",
    name: "Zero to Launch: Digital Product Course",
    shortDescription: "8-module video course: build, price, market, and sell your first digital product — from idea to first $1,000.",
    description:
      "The complete roadmap from idea to profitable digital product. This 8-module course covers market research, product creation, pricing psychology, sales page design, email marketing, launch strategy, and scaling. Includes 40+ video lessons, worksheets, templates, and access to a private community of 2,000+ creators.",
    category: "education",
    productType: "courses",
    priceAmount: 2990,
    currency: "THB",
    coverImageUrl: "https://images.unsplash.com/photo-1522202176988-66273c2fd55f?w=600&h=400&fit=crop",
    badge: "COURSE",
    rating: 4.9,
    reviewCount: 1567,
    salesCount: 6700,
    features: [
      "8 modules, 40+ video lessons",
      "Market research framework",
      "Pricing psychology masterclass",
      "Sales page design templates",
      "Email marketing automation",
      "Launch day playbook",
      "Scaling to $10K/month blueprint",
      "Private community access",
    ],
    testimonials: [
      { name: "Amy Zhang", role: "Course Creator", text: "Made my first $5,000 in the first week after launching. The launch playbook is worth 100x the price.", avatar: "AZ" },
      { name: "Ryan Foster", role: "Side Hustler", text: "Went from zero to $3K/month in 60 days. The community support is incredible.", avatar: "RF" },
    ],
    tags: ["course", "digital-products", "entrepreneurship", "launch", "marketing"],
    deliverables: ["40+ video lessons", "Worksheets and templates", "Private community access", "Lifetime course updates"],
    guaranteeDays: 60,
    lastUpdated: "2026-06-01",
    language: "English",
    difficulty: "beginner",
  },
  {
    id: "prod-018",
    slug: "copywriting-masterclass",
    name: "Copywriting Masterclass Bundle",
    shortDescription: "Complete copywriting training: headlines, emails, sales pages, ads, and more — with real-world examples and exercises.",
    description:
      "Master the art and science of persuasive writing. This bundle includes 20 video lessons covering headline formulas, email copy, sales pages, ad copy, and brand storytelling. Each lesson includes real-world examples from $10M+ campaigns, practice exercises, and a certification quiz. Based on frameworks from David Ogilvy, Gary Halbert, and modern CRO.",
    category: "education",
    productType: "courses",
    priceAmount: 1590,
    currency: "THB",
    coverImageUrl: "https://images.unsplash.com/photo-1455390582262-044cdead277a?w=600&h=400&fit=crop",
    rating: 4.8,
    reviewCount: 892,
    salesCount: 4200,
    features: [
      "20 video lessons with real examples",
      "Headline formula vault (200+ formulas)",
      "Email copywriting framework",
      "Sales page anatomy breakdown",
      "Ad copy for all platforms",
      "Brand storytelling framework",
      "Practice exercises and quizzes",
      "Copywriting certification",
    ],
    testimonials: [
      { name: "Nina Kowalski", role: "Content Marketer", text: "My conversion rates doubled within a month. The headline formulas alone are worth the price.", avatar: "NK" },
    ],
    tags: ["copywriting", "writing", "marketing", "course", "conversion"],
    deliverables: ["20 video lessons", "Formula vault (Notion)", "Practice workbook", "Certification badge"],
    guaranteeDays: 30,
    lastUpdated: "2026-04-18",
    language: "English",
    difficulty: "intermediate",
  },

  // ── Health & Wellness ────────────────────────────────────────────────
  {
    id: "prod-019",
    slug: "meal-prep-nutrition-planner",
    name: "Meal Prep & Nutrition Planner",
    shortDescription: "Weekly meal plans with recipes, grocery lists, macro tracking, and batch cooking guides — eat healthy without the hassle.",
    description:
      "Simplify healthy eating with science-backed meal plans. This planner includes 12 weeks of meal plans (vegetarian, keto, balanced), 100+ recipes with macro breakdowns, auto-generated grocery lists, batch cooking guides, and a nutrition tracking spreadsheet. Designed by a certified nutritionist for busy professionals.",
    category: "health",
    productType: "template",
    priceAmount: 390,
    currency: "THB",
    coverImageUrl: "https://images.unsplash.com/photo-1490645935967-10de6ba17061?w=600&h=400&fit=crop",
    rating: 4.7,
    reviewCount: 2345,
    salesCount: 11500,
    features: [
      "12 weeks of meal plans (3 diet types)",
      "100+ recipes with macro breakdowns",
      "Auto-generated grocery lists",
      "Batch cooking guides",
      "Nutrition tracking spreadsheet",
      "Calorie and macro calculator",
      "Substitution guide for dietary restrictions",
    ],
    testimonials: [
      { name: "Lisa Chen", role: "Busy Professional", text: "I actually look forward to meal prep now. The batch cooking guide saves my Sundays.", avatar: "LC" },
    ],
    tags: ["meal-prep", "nutrition", "health", "recipes", "fitness"],
    deliverables: ["12-week meal plan (PDF + Notion)", "100+ recipe book", "Grocery list templates", "Nutrition tracker"],
    guaranteeDays: 14,
    lastUpdated: "2026-05-22",
    language: "English",
    difficulty: "beginner",
  },
  {
    id: "prod-020",
    slug: "fitness-training-program",
    name: "12-Week Fitness Transformation Program",
    shortDescription: "Progressive overload training program with weekly schedules, exercise library, and progress tracking — home and gym versions.",
    description:
      "Transform your body in 12 weeks with a science-backed progressive overload program. Includes weekly training schedules (4-day and 5-day splits), exercise video library (100+ exercises), warm-up/cool-down routines, deload week protocols, and progress tracking dashboards. Home and gym versions included.",
    category: "health",
    productType: "template",
    priceAmount: 590,
    currency: "THB",
    coverImageUrl: "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=600&h=400&fit=crop",
    rating: 4.8,
    reviewCount: 1890,
    salesCount: 9200,
    features: [
      "12-week progressive overload program",
      "4-day and 5-day training splits",
      "100+ exercise video demonstrations",
      "Home and gym versions",
      "Warm-up and cool-down routines",
      "Deload week protocols",
      "Progress tracking dashboard",
      "Nutrition guidelines included",
    ],
    testimonials: [
      { name: "Jake Williams", role: "Fitness Enthusiast", text: "Gained 12lbs of muscle and lost 8lbs of fat. The progressive overload structure is perfect.", avatar: "JW" },
    ],
    tags: ["fitness", "training", "workout", "health", "strength"],
    deliverables: ["12-week training program", "Exercise video library", "Progress tracker", "Nutrition guidelines"],
    guaranteeDays: 30,
    lastUpdated: "2026-06-05",
    language: "English",
    difficulty: "intermediate",
  },

  // ── Content Creation ─────────────────────────────────────────────────
  {
    id: "prod-021",
    slug: "youtube-growth-toolkit",
    name: "YouTube Growth Toolkit",
    shortDescription: "Thumbnail templates, title formulas, SEO research templates, and content calendars — grow from 0 to 10K subscribers.",
    description:
      "The complete toolkit for growing a YouTube channel from scratch. Includes thumbnail templates (Canva), title and description SEO templates, content calendar, script outlines, analytics dashboard, and a step-by-step growth playbook. Based on analysis of 10K+ successful channels across 20 niches.",
    category: "content",
    productType: "template",
    priceAmount: 790,
    currency: "THB",
    coverImageUrl: "https://images.unsplash.com/photo-1611162617474-5b21e879e113?w=600&h=400&fit=crop",
    badge: "CREATOR FAVORITE",
    rating: 4.8,
    reviewCount: 1234,
    salesCount: 6100,
    features: [
      "Thumbnail templates (Canva, 50+ designs)",
      "Title and description SEO formulas",
      "Content calendar (90 days)",
      "Video script outlines",
      "Analytics tracking dashboard",
      "Growth playbook (0 → 10K subs)",
      "Niche research framework",
    ],
    testimonials: [
      { name: "Alex Turner", role: "YouTuber (45K subs)", text: "Grew from 2K to 45K subscribers in 8 months using this toolkit. The thumbnail templates are 🔥.", avatar: "AT" },
    ],
    tags: ["youtube", "content-creation", "growth", "seo", "thumbnails"],
    deliverables: ["50+ thumbnail templates", "SEO template library", "90-day content calendar", "Growth playbook PDF"],
    guaranteeDays: 30,
    lastUpdated: "2026-05-18",
    language: "English",
    difficulty: "beginner",
  },
  {
    id: "prod-022",
    slug: "podcast-launch-kit",
    name: "Podcast Launch Kit",
    shortDescription: "Everything to launch and grow a podcast: intro/outro templates, show notes templates, guest outreach scripts, and promotion strategies.",
    description:
      "Launch your podcast the right way. This kit includes audio intro/outro templates, show notes templates, guest outreach email sequences, episode planning worksheets, promotion checklists, and a monetization roadmap. Covers equipment recommendations, hosting platform comparison, and RSS distribution strategy.",
    category: "content",
    productType: "template",
    priceAmount: 690,
    currency: "THB",
    coverImageUrl: "https://images.unsplash.com/photo-1478737270239-2f02b77fc618?w=600&h=400&fit=crop",
    rating: 4.6,
    reviewCount: 567,
    salesCount: 2800,
    features: [
      "Audio intro/outro templates (royalty-free)",
      "Show notes templates",
      "Guest outreach email sequences",
      "Episode planning worksheets",
      "Promotion checklists",
      "Monetization roadmap",
      "Equipment buying guide",
    ],
    testimonials: [
      { name: "Sarah Miller", role: "Podcast Host", text: "Launched and hit top 100 in my niche within 3 weeks. The guest outreach scripts are gold.", avatar: "SM" },
    ],
    tags: ["podcast", "content-creation", "audio", "launch", "growth"],
    deliverables: ["Audio templates (royalty-free)", "Notion workspace", "Email templates", "Launch checklist"],
    guaranteeDays: 14,
    lastUpdated: "2026-04-28",
    language: "English",
    difficulty: "beginner",
  },
  {
    id: "prod-023",
    slug: "seo-mastery-guide",
    name: "SEO Mastery Guide",
    shortDescription: "Complete SEO playbook: keyword research, on-page optimization, link building, and technical SEO — rank on page 1.",
    description:
      "Dominate search rankings with a proven SEO strategy. This comprehensive guide covers keyword research methodology, on-page optimization checklists, content cluster strategies, link building outreach templates, technical SEO audits, and local SEO tactics. Includes access to a keyword research spreadsheet with 10,000+ pre-researched keywords across 50 niches.",
    category: "education",
    productType: "ebook",
    priceAmount: 990,
    currency: "THB",
    coverImageUrl: "https://images.unsplash.com/photo-1562577309-4932fdd64cd1?w=600&h=400&fit=crop",
    rating: 4.7,
    reviewCount: 789,
    salesCount: 3900,
    features: [
      "Complete SEO methodology guide",
      "Keyword research framework",
      "On-page optimization checklist",
      "Content cluster strategy",
      "Link building outreach templates",
      "Technical SEO audit guide",
      "10,000+ pre-researched keywords",
      "Local SEO playbook",
    ],
    testimonials: [
      { name: "Brian Lee", role: "SaaS Founder", text: "Went from page 5 to page 1 for our main keyword in 3 months. Organic traffic up 400%.", avatar: "BL" },
    ],
    tags: ["seo", "marketing", "google", "content", "ranking"],
    deliverables: ["SEO guide (PDF + Notion)", "Keyword research spreadsheet", "Audit checklist templates", "Outreach email templates"],
    guaranteeDays: 30,
    lastUpdated: "2026-06-02",
    language: "English",
    difficulty: "intermediate",
  },
  {
    id: "prod-024",
    slug: "notion-project-dashboard",
    name: "Notion Project Dashboard",
    shortDescription: "Multi-project management system with Gantt charts, sprint boards, time tracking, and team collaboration features.",
    description:
      "Manage multiple projects like a pro. This Notion dashboard includes Gantt chart views, sprint planning boards, time tracking, team workload management, risk assessment matrices, and automated status reporting. Supports Scrum, Kanban, and hybrid methodologies. Perfect for teams of 2-20 people.",
    category: "productivity",
    productType: "template",
    priceAmount: 890,
    currency: "THB",
    coverImageUrl: "https://images.unsplash.com/photo-1531403009284-440f080d1e12?w=600&h=400&fit=crop",
    rating: 4.7,
    reviewCount: 456,
    salesCount: 2200,
    features: [
      "Gantt chart view (native Notion)",
      "Sprint planning boards",
      "Time tracking database",
      "Team workload management",
      "Risk assessment matrix",
      "Automated status reporting",
      "Scrum, Kanban, hybrid support",
    ],
    testimonials: [
      { name: "Karen Wu", role: "Project Manager", text: "Replaced Asana for our team of 15. The Gantt charts are surprisingly good for Notion.", avatar: "KW" },
    ],
    tags: ["notion", "project-management", "sprints", "kanban", "teamwork"],
    deliverables: ["Complete Notion workspace", "Setup video tutorial", "Methodology guide", "Lifetime updates"],
    guaranteeDays: 14,
    lastUpdated: "2026-05-15",
    language: "English",
    difficulty: "intermediate",
  },
  {
    id: "prod-025",
    slug: "personal-finance-dashboard",
    name: "Personal Finance Dashboard",
    shortDescription: "Track income, expenses, savings goals, and net worth in one beautiful dashboard — get financial clarity in minutes.",
    description:
      "Take control of your financial life. This comprehensive dashboard tracks income, expenses, savings goals, investments, debt payoff, and net worth. Features include automatic categorization, spending trend analysis, goal progress tracking, and monthly financial health reports. Works in both Notion and Google Sheets.",
    category: "finance",
    productType: "template",
    priceAmount: 590,
    currency: "THB",
    coverImageUrl: "https://images.unsplash.com/photo-1579621970563-ebec7560ff3e?w=600&h=400&fit=crop",
    rating: 4.8,
    reviewCount: 1567,
    salesCount: 8400,
    features: [
      "Income and expense tracking",
      "Savings goal progress bars",
      "Net worth calculator",
      "Debt payoff planner (snowball + avalanche)",
      "Monthly financial health reports",
      "Spending trend analysis",
      "Notion and Google Sheets versions",
    ],
    testimonials: [
      { name: "Mike Johnson", role: "Recent Graduate", text: "Paid off $15K in debt in 8 months using the snowball tracker. This dashboard changed my life.", avatar: "MJ" },
    ],
    tags: ["finance", "budgeting", "notion", "savings", "net-worth"],
    deliverables: ["Notion dashboard", "Google Sheets workbook", "Setup guide", "Budget optimization tips"],
    guaranteeDays: 14,
    lastUpdated: "2026-05-25",
    language: "English",
    difficulty: "beginner",
  },
];

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
      p.tags.some((t) => t.includes(q))
  );
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

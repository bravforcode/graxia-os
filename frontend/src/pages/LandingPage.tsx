import { useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  Zap,
  Shield,
  Star,
  ChevronDown,
  Sparkles,
  Users,
  TrendingUp,
  Lock,
  CreditCard,
  Play,
  Target,
  Layers,
  MousePointer,
  RefreshCw,
  Quote,
  Globe,
} from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import { useLang } from "../i18n/LanguageContext";
import { PRODUCTS, CATEGORY_META, formatPrice, formatSalesCount, getLocalizedName, getLocalizedShortDescription, type ProductCategory } from "../data/products";
import { ANIMATIONS, staggerDelay } from "../lib/animations";
import { ScrollReveal } from "../components/ui/ScrollReveal";

function useInView(options?: IntersectionObserverInit) {
  const ref = useRef<HTMLDivElement>(null);
  const [isInView, setIsInView] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setIsInView(true);
        observer.unobserve(el);
      }
    }, { threshold: 0.1, ...options });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return { ref, isInView };
}

function AnimatedCounter({ value, suffix = "", prefix = "" }: { value: number; suffix?: string; prefix?: string }) {
  const [count, setCount] = useState(0);
  const { ref, isInView } = useInView();

  useEffect(() => {
    if (!isInView) return;
    const duration = 2000;
    const steps = 60;
    const increment = value / steps;
    let current = 0;
    const timer = setInterval(() => {
      current += increment;
      if (current >= value) {
        setCount(value);
        clearInterval(timer);
      } else {
        setCount(Math.floor(current));
      }
    }, duration / steps);
    return () => clearInterval(timer);
  }, [isInView, value]);

  return (
    <span ref={ref} className="tabular-nums">
      {prefix}{count.toLocaleString()}{suffix}
    </span>
  );
}

export default function LandingPage() {
  const { user } = useAuth();
  const { locale, toggle, t } = useLang();
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  useEffect(() => {
    if (user) {
      window.location.href = "/app";
    }
  }, [user]);

  const featuredProducts = PRODUCTS.filter((p) => p.badge).slice(0, 3);

  const faqs = [
    { q: t("faq.q1"), a: t("faq.a1") },
    { q: t("faq.q2"), a: t("faq.a2") },
    { q: t("faq.q3"), a: t("faq.a3") },
    { q: t("faq.q4"), a: t("faq.a4") },
    { q: t("faq.q5"), a: t("faq.a5") },
    { q: t("faq.q6"), a: t("faq.a6") },
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-indigo-500 selection:text-white overflow-x-hidden">
      {/* SEO & Structured Data */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            "@context": "https://schema.org",
            "@type": "Organization",
            name: "Ai Factory",
            url: "https://ai-factory-omega.vercel.app",
            description: t("brand.description"),
            sameAs: [],
          }),
        }}
      />

      {/* Background Effects */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[800px] rounded-full bg-indigo-500/8 blur-[150px]" />
        <div className="absolute bottom-0 right-0 w-[600px] h-[600px] rounded-full bg-cyan-500/6 blur-[120px]" />
        <div className="absolute top-1/2 left-0 w-[400px] h-[400px] rounded-full bg-purple-500/5 blur-[100px]" />
      </div>

      {/* Navigation */}
      <nav className="fixed top-0 left-0 right-0 z-50 border-b border-slate-800/50 bg-slate-950/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-cyan-400 flex items-center justify-center font-mono font-bold text-sm tracking-widest text-slate-950">
              AI
            </div>
            <span className="font-display font-bold text-lg tracking-tight text-white">{t("brand.name")}</span>
          </div>
          <div className="hidden md:flex items-center gap-8 text-sm text-slate-400">
            <a href="#features" className="hover:text-white transition-colors">{t("nav.features")}</a>
            <Link to="/store" className="hover:text-white transition-colors">{t("nav.products")}</Link>
            <a href="#testimonials" className="hover:text-white transition-colors">{t("nav.testimonials")}</a>
            <a href="#pricing" className="hover:text-white transition-colors">{t("nav.pricing")}</a>
            <a href="#faq" className="hover:text-white transition-colors">{t("nav.faq")}</a>
          </div>
          <div className="flex items-center gap-3">
            {/* Language Toggle */}
            <button
              onClick={toggle}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all duration-200 ${ANIMATIONS.buttonPress} ${
                locale === "th"
                  ? "bg-indigo-500/10 border-indigo-500/30 text-indigo-300"
                  : "bg-slate-800/50 border-slate-700/50 text-slate-400 hover:text-white hover:border-slate-600"
              }`}
            >
              <Globe size={14} />
              {t("lang.switch")}
            </button>
            {user ? (
              <Link
                to="/app"
                className={`px-4 py-2 bg-indigo-500 hover:bg-indigo-600 text-white text-sm font-semibold rounded-xl transition-all duration-200 ${ANIMATIONS.buttonPress}`}
              >
                {t("nav.dashboard")}
              </Link>
            ) : (
              <>
                <Link to="/login" className="text-sm text-slate-400 hover:text-white transition-colors">
                  {t("nav.signIn")}
                </Link>
                <Link
                  to="/register"
                  className={`px-4 py-2 bg-indigo-500 hover:bg-indigo-600 text-white text-sm font-semibold rounded-xl transition-all duration-200 shadow-glow-sm ${ANIMATIONS.buttonPress}`}
                >
                  {t("nav.getStarted")}
                </Link>
              </>
            )}
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative pt-32 pb-20 px-6">
        <div className="max-w-5xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-300 text-xs font-semibold mb-8 animate-fade-in">
            <Sparkles size={14} />
            {t("hero.badge")}
          </div>

          <h1 className="text-4xl sm:text-5xl md:text-7xl font-display font-extrabold tracking-tight leading-[1.1] mb-6 animate-fade-in-up">
            <span className="bg-gradient-to-r from-white via-white to-slate-400 bg-clip-text text-transparent">
              {t("hero.title1")}
            </span>
            <br />
            <span className="bg-gradient-to-r from-indigo-400 via-purple-400 to-cyan-400 bg-clip-text text-transparent">
              {t("hero.title2")}
            </span>
          </h1>

          <p className="text-lg md:text-xl text-slate-400 max-w-2xl mx-auto mb-10 leading-relaxed animate-fade-in-up whitespace-pre-line" style={{ animationDelay: "0.1s" }}>
            {t("hero.subtitle")}
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-16 animate-fade-in-up" style={{ animationDelay: "0.2s" }}>
            <Link
              to="/store"
              className={`group px-8 py-4 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white font-bold rounded-2xl shadow-glow-md transition-all duration-200 flex items-center gap-2 text-lg ${ANIMATIONS.buttonPress} ${ANIMATIONS.buttonHover}`}
            >
              {t("hero.cta1")}
              <ArrowRight size={20} className="group-hover:translate-x-1 transition-transform" />
            </Link>
            <a
              href="#features"
              className={`px-8 py-4 bg-slate-800/50 hover:bg-slate-800 text-slate-300 font-semibold rounded-2xl border border-slate-700/50 transition-all duration-200 flex items-center gap-2 ${ANIMATIONS.buttonPress}`}
            >
              <Play size={18} />
              {t("hero.cta2")}
            </a>
          </div>

          <div className="flex flex-wrap items-center justify-center gap-8 text-sm text-slate-500 animate-fade-in" style={{ animationDelay: "0.3s" }}>
            <div className="flex items-center gap-2">
              <div className="flex -space-x-2">
                {["bg-indigo-500", "bg-purple-500", "bg-cyan-500", "bg-emerald-500"].map((bg, i) => (
                  <div key={i} className={`w-8 h-8 rounded-full ${bg} border-2 border-slate-950 flex items-center justify-center text-[10px] font-bold text-white`}>
                    {["S", "M", "A", "R"][i]}
                  </div>
                ))}
              </div>
              <span><AnimatedCounter value={50000} prefix="" suffix="+" /> {t("hero.customers")}</span>
            </div>
            <div className="flex items-center gap-1">
              {[...Array(5)].map((_, i) => (
                <Star key={i} size={14} className="fill-amber-400 text-amber-400" />
              ))}
              <span className="ml-1">4.8 {t("hero.rating")}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Shield size={14} className="text-emerald-400" />
              <span>{t("hero.guarantee")}</span>
            </div>
          </div>
        </div>
      </section>

      {/* Stats Bar */}
      <ScrollReveal delay={100}>
      <section className="border-y border-slate-800/50 bg-slate-900/30 backdrop-blur-xl">
        <div className="max-w-6xl mx-auto px-6 py-12 grid grid-cols-2 md:grid-cols-4 gap-8">
          {[
            { label: t("stats.sold"), value: 85000, suffix: "+", icon: Layers },
            { label: t("stats.customers"), value: 50000, suffix: "+", icon: Users },
            { label: t("stats.rating"), value: 4.8, suffix: "/5", icon: Star },
            { label: t("stats.revenue"), value: 12, suffix: "M+ USD", icon: TrendingUp },
          ].map(({ label, value, suffix, icon: Icon }) => (
            <div key={label} className="text-center group">
              <Icon size={20} className="text-indigo-400 mx-auto mb-2 group-hover:scale-110 transition-transform duration-300" />
              <div className="text-2xl md:text-3xl font-display font-extrabold text-white">
                <AnimatedCounter value={value} suffix={suffix} />
              </div>
              <div className="text-xs text-slate-500 mt-1 uppercase tracking-wider">{label}</div>
            </div>
          ))}
        </div>
      </section>
      </ScrollReveal>

      {/* Featured Products */}
      <ScrollReveal delay={100}>
      <section className="py-20 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-12">
            <span className="text-xs font-semibold text-indigo-400 uppercase tracking-wider">{t("featured.badge")}</span>
            <h2 className="text-3xl md:text-4xl font-display font-extrabold text-white mt-2">{t("featured.title")}</h2>
            <p className="text-slate-400 mt-3 max-w-lg mx-auto">{t("featured.subtitle")}</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {featuredProducts.map((product, i) => (
              <Link
                key={product.id}
                to={`/store/${product.slug}`}
                className={`group bg-slate-900/40 border border-slate-800/80 rounded-3xl overflow-hidden animate-fade-in-up ${ANIMATIONS.cardHoverGlow}`}
                style={staggerDelay(i)}
              >
                <div className="relative h-48 overflow-hidden">
                  <img
                    src={product.coverImageUrl}
                    alt={getLocalizedName(product, locale)}
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                    loading="lazy"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-transparent to-transparent" />
                  {product.badge && (
                    <span className="absolute top-4 left-4 px-3 py-1 bg-indigo-500/90 text-white text-[10px] font-bold uppercase tracking-wider rounded-full">
                      {product.badge}
                    </span>
                  )}
                </div>
                <div className="p-6 space-y-3">
                  <div className="flex items-center gap-2">
                    <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700/50">
                      {CATEGORY_META[product.category].icon} {t(`cat.${product.category}`)}
                    </span>
                    <span className="text-xs text-amber-400 flex items-center gap-0.5">
                      <Star size={10} className="fill-amber-400" /> {product.rating}
                    </span>
                  </div>
                  <h3 className="font-bold text-lg text-white group-hover:text-indigo-300 transition-colors duration-200">{getLocalizedName(product, locale)}</h3>
                  <p className="text-sm text-slate-400 line-clamp-2">{getLocalizedShortDescription(product, locale)}</p>
                  <div className="flex items-center justify-between pt-2">
                    <span className="text-2xl font-extrabold text-white">{formatPrice(product.priceAmount)}</span>
                    <span className="text-xs text-slate-500">{formatSalesCount(product.salesCount)} {t("featured.sold")}</span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
          <div className="text-center mt-10">
            <Link
              to="/store"
              className={`inline-flex items-center gap-2 px-6 py-3 bg-slate-800/50 hover:bg-slate-800 text-white font-semibold rounded-2xl border border-slate-700/50 transition-all duration-200 ${ANIMATIONS.buttonPress}`}
            >
              {t("featured.viewAll", { count: PRODUCTS.length })}
              <ArrowRight size={16} />
            </Link>
          </div>
        </div>
      </section>
      </ScrollReveal>

      {/* Categories Grid */}
      <ScrollReveal delay={100}>
      <section className="py-20 px-6 bg-slate-900/20">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-12">
            <span className="text-xs font-semibold text-cyan-400 uppercase tracking-wider">{t("categories.badge")}</span>
            <h2 className="text-3xl md:text-4xl font-display font-extrabold text-white mt-2">{t("categories.title")}</h2>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
            {(Object.entries(CATEGORY_META) as [ProductCategory, typeof CATEGORY_META[ProductCategory]][]).map(([key, cat], i) => {
              const count = PRODUCTS.filter((p) => p.category === key).length;
              return (
                <Link
                  key={key}
                  to={`/store?category=${key}`}
                  className={`group p-5 bg-slate-900/40 border border-slate-800/60 rounded-2xl hover:border-indigo-500/30 transition-all duration-300 text-center space-y-3 animate-fade-in-up ${ANIMATIONS.cardHoverGlow}`}
                  style={staggerDelay(i)}
                >
                  <span className="text-3xl group-hover:scale-125 transition-transform duration-300 inline-block">{cat.icon}</span>
                  <h3 className="font-semibold text-sm text-white group-hover:text-indigo-300 transition-colors duration-200">{t(`cat.${key}`)}</h3>
                  <p className="text-[10px] text-slate-500">{count} {t("store.products")}</p>
                </Link>
              );
            })}
          </div>
        </div>
      </section>
      </ScrollReveal>

      {/* Features */}
      <ScrollReveal delay={100}>
      <section id="features" className="py-20 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <span className="text-xs font-semibold text-purple-400 uppercase tracking-wider">{t("features.badge")}</span>
            <h2 className="text-3xl md:text-4xl font-display font-extrabold text-white mt-2">
              {(() => {
                const parts = t("features.title").split("||");
                return parts.length > 1 ? (
                  <>
                    {parts[0]}
                    <span className="bg-gradient-to-r from-indigo-400 to-cyan-400 bg-clip-text text-transparent">{parts[1]}</span>
                  </>
                ) : (
                  t("features.title")
                );
              })()}
            </h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {[
              { icon: Zap, titleKey: "features.instant.title", descKey: "features.instant.desc", color: "from-amber-500 to-orange-600" },
              { icon: Shield, titleKey: "features.quality.title", descKey: "features.quality.desc", color: "from-emerald-500 to-green-600" },
              { icon: TrendingUp, titleKey: "features.roi.title", descKey: "features.roi.desc", color: "from-indigo-500 to-purple-600" },
              { icon: RefreshCw, titleKey: "features.updates.title", descKey: "features.updates.desc", color: "from-cyan-500 to-blue-600" },
              { icon: Lock, titleKey: "features.secure.title", descKey: "features.secure.desc", color: "from-rose-500 to-pink-600" },
              { icon: Target, titleKey: "features.guarantee.title", descKey: "features.guarantee.desc", color: "from-violet-500 to-purple-600" },
            ].map(({ icon: Icon, titleKey, descKey, color }) => (
              <div
                key={titleKey}
                className={`p-6 bg-slate-900/40 border border-slate-800/60 rounded-3xl hover:border-slate-700/80 transition-all duration-300 group ${ANIMATIONS.cardHover}`}
              >
                <div className={`w-12 h-12 rounded-2xl bg-gradient-to-br ${color} flex items-center justify-center text-white mb-4 group-hover:scale-110 transition-transform duration-300`}>
                  <Icon size={22} />
                </div>
                <h3 className="font-bold text-lg text-white mb-2">{t(titleKey)}</h3>
                <p className="text-sm text-slate-400 leading-relaxed">{t(descKey)}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
      </ScrollReveal>

      {/* How It Works */}
      <ScrollReveal delay={100}>
      <section className="py-20 px-6 bg-slate-900/20">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-16">
            <span className="text-xs font-semibold text-emerald-400 uppercase tracking-wider">{t("howItWorks.badge")}</span>
            <h2 className="text-3xl md:text-4xl font-display font-extrabold text-white mt-2">{t("howItWorks.title")}</h2>
          </div>
          <div className="space-y-8">
            {[
              { step: "01", titleKey: "howItWorks.step1.title", descKey: "howItWorks.step1.desc", icon: MousePointer },
              { step: "02", titleKey: "howItWorks.step2.title", descKey: "howItWorks.step2.desc", icon: CreditCard },
              { step: "03", titleKey: "howItWorks.step3.title", descKey: "howItWorks.step3.desc", icon: Sparkles },
            ].map(({ step, titleKey, descKey }, i) => (
              <div
                key={step}
                className="flex items-start gap-6 p-6 bg-slate-900/40 border border-slate-800/60 rounded-3xl group hover:border-slate-700/80 transition-all duration-300 animate-fade-in-up"
                style={staggerDelay(i)}
              >
                <div className="flex-shrink-0 w-14 h-14 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white font-display font-bold text-lg group-hover:scale-110 transition-transform duration-300">
                  {step}
                </div>
                <div>
                  <h3 className="font-bold text-lg text-white mb-1">{t(titleKey)}</h3>
                  <p className="text-sm text-slate-400 leading-relaxed">{t(descKey)}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
      </ScrollReveal>

      {/* Testimonials */}
      <ScrollReveal delay={100}>
      <section id="testimonials" className="py-20 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-12">
            <span className="text-xs font-semibold text-amber-400 uppercase tracking-wider">{t("testimonials.badge")}</span>
            <h2 className="text-3xl md:text-4xl font-display font-extrabold text-white mt-2">{t("testimonials.title")}</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              { name: "Sarah Chen", role: locale === "th" ? "ผู้อำนวยการฝ่ายการตลาด" : "Marketing Director", text: locale === "th" ? "ชุด AI Prompts ช่วยให้ทีมเราประหยัดเวลา 15+ ชั่วโมงต่อสัปดาห์ ROI ทันที เราคืนทุนในวันแรก" : "The AI prompts bundle saved our team 15+ hours per week. The ROI was immediate — we recouped the cost in the first day.", avatar: "SC", color: "bg-indigo-500" },
              { name: "Marcus Rivera", role: locale === "th" ? "Indie Hacker" : "Indie Hacker", text: locale === "th" ? "เปิดตัว SaaS ใน 3 วันด้วย boilerplate kit ถ้าทำเองคงต้องใช้เวลาหลายเดือน  инвестицияที่ดีที่สุด" : "I launched my SaaS in 3 days with the boilerplate kit. Would have taken me months otherwise. Best investment I've made.", avatar: "MR", color: "bg-purple-500" },
              { name: "Lisa Wong", role: locale === "th" ? "ครีเอเตอร์ (200K ผู้ติดตาม)" : "Content Creator (200K)", text: locale === "th" ? "เทมเพลตโซเชียลมีเดียเปลี่ยนกลยุทธ์เนื้อหาของเรา Interaction เพิ่มขึ้น 340% ในเดือนแรก" : "The social media templates transformed my content strategy. Engagement went up 340% in the first month. Absolutely insane results.", avatar: "LW", color: "bg-cyan-500" },
              { name: "David Park", role: locale === "th" ? "ผู้ก่อตั้ง E-commerce" : "E-commerce Founder", text: locale === "th" ? "Conversion Rate หน้าสินค้าเพิ่มจาก 2.1% เป็น 5.8% ด้วยเทมเพลต copywriting คุ้มค่าทุกบาท" : "My product page conversion rate jumped from 2.1% to 5.8% using the copywriting templates. Worth every penny and then some.", avatar: "DP", color: "bg-emerald-500" },
              { name: "Emma Rodriguez", role: locale === "th" ? "Product Manager" : "Product Manager", text: locale === "th" ? "Notion Life OS เป็นเทมเพลตเดียวที่ใช้จริงจัง 6 เดือนแล้ว ชีวิตมีระเบียบเป็นครั้งแรก" : "The Notion Life OS is the only template that stuck. 6 months in and my entire life is organized. I've tried dozens of others.", avatar: "ER", color: "bg-amber-500" },
              { name: "Kevin O'Brien", role: locale === "th" ? "Full-Stack Developer" : "Full-Stack Developer", text: locale === "th" ? "โค้ดสะอาด เอกสารดี ทุกอย่างทำงานได้ทันที Component library แทนระบบ in-house ได้เลย" : "Clean code, great docs, and everything just works. The component library replaced our entire in-house system.", avatar: "KO", color: "bg-rose-500" },
            ].map(({ name, role, text, avatar, color }) => (
              <div key={name} className={`p-6 bg-slate-900/40 border border-slate-800/60 rounded-3xl hover:border-slate-700/80 transition-all duration-300 group ${ANIMATIONS.cardHover}`}>
                <Quote size={20} className="text-indigo-500/30 mb-3 group-hover:text-indigo-500/50 transition-colors duration-300" />
                <p className="text-sm text-slate-300 leading-relaxed mb-4">"{text}"</p>
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-full ${color} flex items-center justify-center text-white text-xs font-bold group-hover:scale-110 transition-transform duration-300`}>
                    {avatar}
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-white">{name}</div>
                    <div className="text-xs text-slate-500">{role}</div>
                  </div>
                  <div className="ml-auto flex gap-0.5">
                    {[...Array(5)].map((_, i) => (
                      <Star key={i} size={10} className="fill-amber-400 text-amber-400" />
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
      </ScrollReveal>

      {/* Pricing */}
      <ScrollReveal delay={100}>
      <section id="pricing" className="py-20 px-6 bg-slate-900/20">
        <div className="max-w-4xl mx-auto text-center">
          <span className="text-xs font-semibold text-indigo-400 uppercase tracking-wider">{t("pricing.badge")}</span>
          <h2 className="text-3xl md:text-4xl font-display font-extrabold text-white mt-2 mb-4">
            {t("pricing.title")}
          </h2>
          <p className="text-slate-400 mb-10 max-w-xl mx-auto">
            {t("pricing.subtitle")}
          </p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              { range: "<฿1,000", count: PRODUCTS.filter((p) => p.priceAmount < 1000).length, labelKey: "pricing.quickWins" },
              { range: "฿1,000–฿2,000", count: PRODUCTS.filter((p) => p.priceAmount >= 1000 && p.priceAmount < 2000).length, labelKey: "pricing.proTools" },
              { range: "฿2,000+", count: PRODUCTS.filter((p) => p.priceAmount >= 2000).length, labelKey: "pricing.premium" },
            ].map(({ range, count, labelKey }) => (
              <div key={range} className={`p-6 bg-slate-900/40 border border-slate-800/60 rounded-3xl transition-all duration-300 hover:border-slate-700/80 ${ANIMATIONS.cardHover}`}>
                <div className="text-3xl font-display font-extrabold text-white mb-1">{range}</div>
                <div className="text-sm text-indigo-400 font-semibold mb-2">{count} {t("store.products")}</div>
                <div className="text-xs text-slate-500">{t(labelKey)}</div>
              </div>
            ))}
          </div>
          <div className="mt-10 inline-flex items-center gap-2 px-4 py-2 bg-emerald-500/10 border border-emerald-500/20 rounded-full text-sm text-emerald-400">
            <Shield size={16} />
            {t("pricing.guarantee")}
          </div>
        </div>
      </section>
      </ScrollReveal>

      {/* FAQ */}
      <ScrollReveal delay={100}>
      <section id="faq" className="py-20 px-6">
        <div className="max-w-3xl mx-auto">
          <div className="text-center mb-12">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{t("faq.badge")}</span>
            <h2 className="text-3xl md:text-4xl font-display font-extrabold text-white mt-2">{t("faq.title")}</h2>
          </div>
          <div className="space-y-3">
            {faqs.map((faq, i) => (
              <div key={i} className="border border-slate-800/60 rounded-2xl overflow-hidden">
                <button
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                  aria-expanded={openFaq === i}
                  className="w-full flex items-center justify-between p-5 text-left bg-slate-900/30 hover:bg-slate-900/50 transition-colors duration-200"
                >
                  <span className="font-semibold text-sm text-white pr-4">{faq.q}</span>
                  <ChevronDown
                    size={18}
                    className={`text-slate-400 shrink-0 transition-transform duration-300 ${openFaq === i ? "rotate-180" : ""}`}
                  />
                </button>
                <div
                  className={`overflow-hidden transition-all duration-300 ease-out ${
                    openFaq === i ? "max-h-96 opacity-100" : "max-h-0 opacity-0"
                  }`}
                >
                  <div className="px-5 pb-5 text-sm text-slate-400 leading-relaxed bg-slate-900/20">
                    {faq.a}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
      </ScrollReveal>

      {/* Final CTA */}
      <ScrollReveal delay={100}>
      <section className="py-20 px-6">
        <div className="max-w-4xl mx-auto text-center">
          <div className="p-12 bg-gradient-to-br from-indigo-500/10 via-purple-500/5 to-cyan-500/10 border border-indigo-500/20 rounded-[2rem] relative overflow-hidden">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(99,102,241,0.15),transparent_70%)]" />
            <div className="relative z-10">
              <h2 className="text-3xl md:text-4xl font-display font-extrabold text-white mb-4">
                {t("cta.title")}
              </h2>
              <p className="text-slate-400 mb-8 max-w-lg mx-auto">
                {t("cta.subtitle")}
              </p>
              <Link
                to="/store"
                className={`inline-flex items-center gap-2 px-8 py-4 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white font-bold rounded-2xl shadow-glow-md transition-all duration-200 text-lg ${ANIMATIONS.buttonPress} ${ANIMATIONS.buttonHover}`}
              >
                {t("cta.button")}
                <ArrowRight size={20} />
              </Link>
            </div>
          </div>
        </div>
      </section>
      </ScrollReveal>

      {/* Footer */}
      <footer className="border-t border-slate-800/50 py-12 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-10">
            <div>
              <div className="flex items-center gap-2 mb-4">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-cyan-400 flex items-center justify-center font-mono font-bold text-xs text-slate-950">AI</div>
                <span className="font-display font-bold text-white">{t("brand.name")}</span>
              </div>
              <p className="text-xs text-slate-500 leading-relaxed">{t("brand.description")}</p>
            </div>
            <div>
              <h4 className="text-xs font-bold text-white uppercase tracking-wider mb-3">{t("footer.products")}</h4>
              <div className="space-y-2 text-xs text-slate-500">
                <Link to="/store?category=ai-automation" className="block hover:text-white transition-colors duration-200">{t("cat.ai-automation")}</Link>
                <Link to="/store?category=productivity" className="block hover:text-white transition-colors duration-200">{t("cat.productivity")}</Link>
                <Link to="/store?category=design" className="block hover:text-white transition-colors duration-200">{t("cat.design")}</Link>
                <Link to="/store?category=developer" className="block hover:text-white transition-colors duration-200">{t("cat.developer")}</Link>
              </div>
            </div>
            <div>
              <h4 className="text-xs font-bold text-white uppercase tracking-wider mb-3">{t("footer.resources")}</h4>
              <div className="space-y-2 text-xs text-slate-500">
                <span className="block">{t("footer.blog")}</span>
                <span className="block">{t("footer.helpCenter")}</span>
                <span className="block">{t("footer.affiliate")}</span>
                <span className="block">{t("footer.becomeCreator")}</span>
              </div>
            </div>
            <div>
              <h4 className="text-xs font-bold text-white uppercase tracking-wider mb-3">{t("footer.legal")}</h4>
              <div className="space-y-2 text-xs text-slate-500">
                <span className="block">{t("footer.terms")}</span>
                <span className="block">{t("footer.privacy")}</span>
                <span className="block">{t("footer.refund")}</span>
                <span className="block">{t("footer.license")}</span>
              </div>
            </div>
          </div>
          <div className="border-t border-slate-800/50 pt-6 flex flex-col md:flex-row items-center justify-between gap-4">
            <p className="text-xs text-slate-600">{t("footer.copyright")}</p>
            <div className="flex items-center gap-1.5 text-xs text-slate-600">
              <Lock size={12} className="text-emerald-500/60" />
              {t("footer.secured")}
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

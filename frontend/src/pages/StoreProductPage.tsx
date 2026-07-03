import { useParams, Link } from "react-router-dom";
import {
  ArrowLeft, Star, Users, Download, Check, ChevronDown,
  ShieldCheck, Award, Clock, ArrowRight, CheckCircle, Gift,
  TrendingUp, Globe,
} from "lucide-react";
import { useState, useEffect } from "react";
import { useLang } from "../i18n/LanguageContext";
import { PRODUCTS, CATEGORY_META, formatPrice, formatSalesCount, getLocalizedName, getLocalizedShortDescription, getLocalizedDescription, type ProductCatalogItem } from "../data/products";
import { ANIMATIONS, staggerDelay } from "../lib/animations";
import { ScrollReveal } from "../components/ui/ScrollReveal";
import { SkeletonProductDetail } from "../components/ui/Skeleton";

export default function StoreProductPage() {
  const { slug } = useParams<{ slug: string }>();
  const [product, setProduct] = useState<ProductCatalogItem | null>(null);
  const [openFaq, setOpenFaq] = useState<number | null>(null);
  const { locale, toggle, t } = useLang();
  const [timeLeft, setTimeLeft] = useState({ hours: 23, minutes: 47, seconds: 33 });

  useEffect(() => {
    if (slug) { const found = PRODUCTS.find((p) => p.slug === slug); setProduct(found || null); }
  }, [slug]);

  useEffect(() => {
    const timer = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev.seconds > 0) return { ...prev, seconds: prev.seconds - 1 };
        if (prev.minutes > 0) return { ...prev, minutes: prev.minutes - 1, seconds: 59 };
        if (prev.hours > 0) return { hours: prev.hours - 1, minutes: 59, seconds: 59 };
        return prev;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const [isPageLoading, setIsPageLoading] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => setIsPageLoading(false), 200);
    return () => clearTimeout(timer);
  }, []);

  if (isPageLoading && product === null) {
    return <SkeletonProductDetail />;
  }

  if (!product) {
    return (
      <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center text-slate-400 p-6">
        <h2 className="text-2xl font-bold text-slate-100 mb-2">{t("product.notFound")}</h2>
        <p className="text-sm text-slate-500 mb-4">{t("product.notFoundDesc")}</p>
        <Link to="/store" className={`px-4 py-2 bg-indigo-500 hover:bg-indigo-600 text-white text-sm font-semibold rounded-xl transition-all duration-200 ${ANIMATIONS.buttonPress}`}>
          {t("product.browseStore")}
        </Link>
      </div>
    );
  }

  const faqs = [
    { q: t("faq.q1"), a: t("faq.a1") },
    { q: t("faq.q2"), a: t("faq.a2") },
    { q: t("faq.q3"), a: t("faq.a3") },
    { q: t("faq.q5"), a: t("faq.a5") },
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-indigo-500 selection:text-white">
      {/* SEO Structured Data */}
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify({
        "@context": "https://schema.org", "@type": "Product",
        name: product.name, description: product.shortDescription, image: product.coverImageUrl,
        offers: { "@type": "Offer", price: product.priceAmount, priceCurrency: product.currency, availability: "https://schema.org/InStock" },
        aggregateRating: { "@type": "AggregateRating", ratingValue: product.rating, reviewCount: product.reviewCount },
      }) }} />

      {/* Background */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] rounded-full bg-indigo-500/8 blur-[120px]" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] rounded-full bg-cyan-500/6 blur-[120px]" />
      </div>

      {/* Sticky Header */}
      <div className="fixed top-0 left-0 right-0 z-50 border-b border-slate-800/50 bg-slate-950/90 backdrop-blur-xl">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <Link to="/store" className="flex items-center gap-2 text-slate-400 hover:text-white text-sm transition-colors duration-200">
            <ArrowLeft size={16} /><span className="hidden sm:inline">{t("product.backToStore")}</span>
          </Link>
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-cyan-400 flex items-center justify-center font-mono font-bold text-[10px] text-slate-950">AI</div>
            <span className="font-display font-bold text-sm text-white">{t("brand.name")}</span>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={toggle}
              className={`flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-semibold border transition-all duration-200 ${ANIMATIONS.buttonPress} ${
                locale === "th" ? "bg-indigo-500/10 border-indigo-500/30 text-indigo-300" : "bg-slate-800/50 border-slate-700/50 text-slate-400"
              }`}>
              <Globe size={10} />{t("lang.switch")}
            </button>
            <span className="hidden sm:inline text-xs text-slate-400 font-mono">{formatPrice(product.priceAmount)}</span>
            <button onClick={() => document.getElementById("checkout")?.scrollIntoView({ behavior: "smooth" })}
              className={`px-4 py-1.5 bg-indigo-500 hover:bg-indigo-600 text-white text-xs font-semibold rounded-xl transition-all duration-200 ${ANIMATIONS.buttonPress}`}>
              {t("product.buyNow")}
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 pt-20 pb-16 relative z-10 space-y-16">
        {/* Hero Section */}
        <ScrollReveal>
        <section className="grid grid-cols-1 lg:grid-cols-12 gap-10 items-start">
          <div className="lg:col-span-7 space-y-6 pt-4">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
                {CATEGORY_META[product.category].icon} {t(`cat.${product.category}`)}
              </span>
              {product.badge && <span className="px-2.5 py-1 bg-amber-500/10 text-amber-300 border border-amber-500/20 rounded-full text-[10px] font-bold uppercase tracking-wider">{product.badge}</span>}
              <span className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">{product.difficulty}</span>
            </div>

            <h1 className="text-3xl sm:text-4xl md:text-5xl font-display font-extrabold tracking-tight leading-[1.1]">
              <span className="bg-gradient-to-r from-white via-white to-slate-300 bg-clip-text text-transparent">{getLocalizedName(product, locale)}</span>
            </h1>

            <p className="text-lg text-slate-300 font-medium leading-relaxed max-w-2xl">{getLocalizedShortDescription(product, locale)}</p>

            <div className="flex flex-wrap items-center gap-4 text-sm">
              <div className="flex items-center gap-1.5">
                {[...Array(5)].map((_, i) => <Star key={i} size={14} className="fill-amber-400 text-amber-400" />)}
                <span className="text-slate-300 font-semibold ml-1">{product.rating}</span>
                <span className="text-slate-500">({product.reviewCount.toLocaleString()} reviews)</span>
              </div>
              <span className="text-slate-600">·</span>
              <div className="flex items-center gap-1.5 text-slate-400"><Users size={14} /><span>{formatSalesCount(product.salesCount)} {t("featured.sold")}</span></div>
              <span className="text-slate-600">·</span>
              <span className="text-slate-400">Updated {new Date(product.lastUpdated).toLocaleDateString(locale === "th" ? "th-TH" : "en-US", { month: "short", year: "numeric" })}</span>
            </div>

            <div className="space-y-3 pt-2">
              <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider">{t("product.whatsIncluded")}</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                {product.features.map((f, i) => (
                  <div key={i} className="flex items-start gap-2.5 text-sm text-slate-400">
                    <Check size={16} className="text-emerald-400 mt-0.5 shrink-0" /><span>{f}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="pt-4 text-sm text-slate-400 leading-relaxed space-y-4"><p>{getLocalizedDescription(product, locale)}</p></div>
          </div>

          {/* Checkout Card */}
          <div id="checkout" className="lg:col-span-5 space-y-5 sticky top-20">
            <div className="bg-slate-900/40 border border-slate-800 rounded-3xl p-6 shadow-2xl backdrop-blur-xl space-y-5 relative overflow-hidden">
              <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-bl from-indigo-500/10 to-transparent blur-xl pointer-events-none" />
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider">{t("product.premiumAccess")}</span>
                  {product.badge && <span className="px-2 py-0.5 bg-emerald-500/10 text-emerald-400 text-[10px] font-bold rounded-full border border-emerald-500/20">{product.badge}</span>}
                </div>
                <div className="flex items-baseline gap-2 mt-2">
                  <span className="text-4xl font-extrabold text-white">{formatPrice(product.priceAmount)}</span>
                  <span className="text-sm text-slate-500 line-through">{formatPrice(Math.round(product.priceAmount * 1.5))}</span>
                </div>
                <p className="text-[10px] text-slate-500 mt-1">{t("product.oneTime")} · {product.guaranteeDays}-day guarantee</p>
              </div>

              <Link to={`/f/demo/${product.slug}`}
                className={`w-full py-4 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white font-bold rounded-xl shadow-glow-md transition-all duration-200 flex items-center justify-center gap-2 group text-sm ${ANIMATIONS.buttonPress} ${ANIMATIONS.buttonHover}`}>
                {t("product.getInstantAccess")}
                <ArrowRight size={16} className="group-hover:translate-x-0.5 transition-transform" />
              </Link>

              <div className="space-y-2.5 text-xs text-slate-500">
                {[
                  { icon: CheckCircle, text: t("product.instantAccess") },
                  { icon: ShieldCheck, text: t("product.stripeEncrypted") },
                  { icon: Award, text: `${product.guaranteeDays}-day ${t("product.moneyBack")}` },
                  { icon: TrendingUp, text: `${formatSalesCount(product.salesCount)} ${t("product.happyCustomers")}` },
                ].map(({ icon: Icon, text }) => (
                  <div key={text} className="flex items-center gap-2"><Icon size={14} className="text-emerald-500" /><span>{text}</span></div>
                ))}
              </div>

              <div className="p-3 bg-amber-500/5 border border-amber-500/10 rounded-xl text-center">
                <div className="flex items-center justify-center gap-1.5 text-xs text-amber-400 font-semibold">
                  <Clock size={12} />{t("product.limitedOffer")}
                </div>
                <div className="flex items-center justify-center gap-3 mt-2 font-mono text-lg text-white font-bold">
                  <span>{String(timeLeft.hours).padStart(2, "0")}</span>
                  <span className="text-amber-400">:</span>
                  <span>{String(timeLeft.minutes).padStart(2, "0")}</span>
                  <span className="text-amber-400">:</span>
                  <span>{String(timeLeft.seconds).padStart(2, "0")}</span>
                </div>
              </div>
            </div>

            {/* Lead Magnet */}
            <div className="bg-slate-900/20 border border-slate-800/60 rounded-3xl p-5 shadow-xl backdrop-blur-xl space-y-3">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-indigo-500/10 rounded-xl text-indigo-400"><Gift size={16} /></div>
                <div>
                  <h4 className="text-xs font-bold text-white">{t("product.freeSample")}</h4>
                  <p className="text-[10px] text-slate-500">{t("product.freeSampleDesc")}</p>
                </div>
              </div>
              <form className="space-y-2" onSubmit={(e) => e.preventDefault()}>
                <div className="grid grid-cols-2 gap-2">
                  <input type="text" placeholder="Name" className="bg-slate-950 border border-slate-800 text-slate-300 px-3 py-2 rounded-xl text-xs outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all duration-200" />
                  <input type="email" required placeholder="Email" className="bg-slate-950 border border-slate-800 text-slate-300 px-3 py-2 rounded-xl text-xs outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all duration-200" />
                </div>
                <button type="submit" className={`w-full py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-xl transition-all duration-200 ${ANIMATIONS.buttonPress}`}>
                  {t("product.getFreeSample")}
                </button>
              </form>
            </div>
          </div>
        </section>
        </ScrollReveal>

        {/* Testimonials */}
        {product.testimonials.length > 0 && (
          <ScrollReveal delay={100}>
          <section>
            <h2 className="text-2xl font-display font-extrabold text-white mb-6">{t("product.customersSay")}</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {product.testimonials.map((testimonial, i) => (
                <div key={i} className={`p-5 bg-slate-900/40 border border-slate-800/60 rounded-2xl space-y-3 animate-fade-in-up ${ANIMATIONS.cardHover}`} style={staggerDelay(i)}>
                  <div className="flex gap-0.5">{[...Array(5)].map((_, j) => <Star key={j} size={12} className="fill-amber-400 text-amber-400" />)}</div>
                  <p className="text-sm text-slate-300 leading-relaxed">"{testimonial.text}"</p>
                  <div className="flex items-center gap-2.5 pt-1">
                    <div className="w-8 h-8 rounded-full bg-indigo-500 flex items-center justify-center text-white text-[10px] font-bold">{testimonial.avatar}</div>
                    <div>
                      <div className="text-xs font-semibold text-white">{testimonial.name}</div>
                      <div className="text-[10px] text-slate-500">{testimonial.role}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>
          </ScrollReveal>
        )}

        {/* Deliverables */}
        <ScrollReveal delay={100}>
        <section>
          <h2 className="text-2xl font-display font-extrabold text-white mb-6">{t("product.youllReceive")}</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {product.deliverables.map((d, i) => (
              <div key={i} className="flex items-center gap-3 p-4 bg-slate-900/30 border border-slate-800/50 rounded-xl hover:border-slate-700/80 transition-all duration-200">
                <div className="w-8 h-8 rounded-lg bg-indigo-500/10 flex items-center justify-center text-indigo-400 shrink-0"><Download size={14} /></div>
                <span className="text-sm text-slate-300">{d}</span>
              </div>
            ))}
          </div>
        </section>
        </ScrollReveal>

        {/* FAQ */}
        <ScrollReveal delay={100}>
        <section>
          <h2 className="text-2xl font-display font-extrabold text-white mb-6">{t("product.faqTitle")}</h2>
          <div className="space-y-3 max-w-3xl">
            {faqs.map((faq, i) => (
              <div key={i} className="border border-slate-800/60 rounded-2xl overflow-hidden">
                <button onClick={() => setOpenFaq(openFaq === i ? null : i)} aria-expanded={openFaq === i}
                  className="w-full flex items-center justify-between p-5 text-left bg-slate-900/30 hover:bg-slate-900/50 transition-colors duration-200">
                  <span className="font-semibold text-sm text-white pr-4">{faq.q}</span>
                  <ChevronDown size={16} className={`text-slate-400 shrink-0 transition-transform duration-300 ${openFaq === i ? "rotate-180" : ""}`} />
                </button>
                <div className={`overflow-hidden transition-all duration-300 ease-out ${openFaq === i ? "max-h-96 opacity-100" : "max-h-0 opacity-0"}`}>
                  <div className="px-5 pb-5 text-sm text-slate-400 leading-relaxed bg-slate-900/20">{faq.a}</div>
                </div>
              </div>
            ))}
          </div>
        </section>
        </ScrollReveal>

        {/* Final CTA */}
        <ScrollReveal delay={100}>
        <section className="text-center">
          <div className="p-10 bg-gradient-to-br from-indigo-500/10 via-purple-500/5 to-cyan-500/10 border border-indigo-500/20 rounded-3xl relative overflow-hidden">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(99,102,241,0.1),transparent_70%)]" />
            <div className="relative z-10 space-y-4">
              <h2 className="text-2xl md:text-3xl font-display font-extrabold text-white">{t("product.readyToStart")}</h2>
              <p className="text-slate-400 max-w-md mx-auto text-sm">
                {formatSalesCount(product.salesCount)} {t("product.joinCustomers")}
              </p>
              <Link to={`/f/demo/${product.slug}`}
                className={`inline-flex items-center gap-2 px-8 py-4 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white font-bold rounded-2xl shadow-glow-md transition-all duration-200 ${ANIMATIONS.buttonPress} ${ANIMATIONS.buttonHover}`}>
                {t("product.buyNow")} — {formatPrice(product.priceAmount)}
                <ArrowRight size={18} />
              </Link>
              <div className="flex items-center justify-center gap-1.5 text-xs text-slate-500">
                <ShieldCheck size={12} className="text-emerald-500/60" />
                {product.guaranteeDays}-day money-back guarantee · {t("store.trust2")}
              </div>
            </div>
          </div>
        </section>
        </ScrollReveal>
      </div>
    </div>
  );
}

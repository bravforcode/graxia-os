import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  CheckCircle, ArrowRight, Mail, ShieldCheck, Download,
  AlertTriangle, Gift, Star, ChevronDown, Clock, Check, Users,
  Lock, Award, ArrowLeft,
} from "lucide-react";
import { useLang } from "../../i18n/LanguageContext";
import { PRODUCTS, CATEGORY_META, formatPrice, formatSalesCount, type ProductCatalogItem } from "../../data/products";
import { funnelApi, type DigitalProduct } from "../../api/funnel";
import { ANIMATIONS, staggerDelay } from "../../lib/animations";
import { ScrollReveal } from "../../components/ui/ScrollReveal";
import { SkeletonProductDetail } from "../../components/ui/Skeleton";

export default function PublicProductPage() {
  const { organization_id, slug } = useParams<{ organization_id: string; slug: string }>();
  const { locale, toggle, t } = useLang();
  const [product, setProduct] = useState<DigitalProduct | null>(null);
  const [catalogProduct, setCatalogProduct] = useState<ProductCatalogItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState("");

  // Checkout form
  const [email, setEmail] = useState("");
  const [checkingOut, setCheckingOut] = useState(false);

  // Lead Magnet
  const [leadEmail, setLeadEmail] = useState("");
  const [leadName, setLeadName] = useState("");
  const [submittingLead, setSubmittingLead] = useState(false);
  const [leadSuccessMsg, setLeadSuccessMsg] = useState("");
  const [leadDownloadUrl, setLeadDownloadUrl] = useState("");

  // FAQ accordion
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  // Countdown timer
  const [timeLeft, setTimeLeft] = useState({ hours: 23, minutes: 47, seconds: 33 });

  const orgId = organization_id || "";
  const productSlug = slug || "";

  useEffect(() => {
    if (orgId && productSlug) {
      loadProduct();
    }
  }, [orgId, productSlug]);

  // Countdown timer
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

  // Match catalog product
  useEffect(() => {
    if (productSlug) {
      const match = PRODUCTS.find((p) => p.slug === productSlug);
      setCatalogProduct(match || null);
    }
  }, [productSlug]);

  const loadProduct = async () => {
    try {
      setLoading(true);
      setErrorMsg("");
      const data = await funnelApi.getPublicProduct(orgId, productSlug);
      setProduct(data);

      await funnelApi.logPublicEvent({
        organization_id: orgId,
        event_type: "product_view",
        product_id: data.id,
        referrer: document.referrer || undefined,
      }).catch(() => {});
    } catch (err: any) {
      console.error("Failed to retrieve public product", err);
      setErrorMsg(err.response?.data?.detail || "Product not found or currently unavailable.");
    } finally {
      setLoading(false);
    }
  };

  const handleCheckout = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!product) return;
    if (!email.trim()) {
      alert(locale === "th" ? "กรุณากรอกอีเมลที่ถูกต้อง" : "Please enter a valid email address.");
      return;
    }

    try {
      setCheckingOut(true);

      await funnelApi.logPublicEvent({
        organization_id: orgId,
        event_type: "checkout_start",
        product_id: product.id,
        metadata_json: { email: email.trim() },
      }).catch(() => {});

      const successUrl = `${window.location.origin}/checkout/success?session_id={CHECKOUT_SESSION_ID}`;
      const cancelUrl = window.location.href;

      const checkout = await funnelApi.createPublicCheckoutSession(product.id, {
        organization_id: orgId,
        customer_email: email.trim(),
        success_url: successUrl,
        cancel_url: cancelUrl,
      });

      if (checkout.checkout_url) {
        window.location.href = checkout.checkout_url;
      } else {
        alert(locale === "th" ? "ไม่สามารถเริ่มกระบวนการชำระเงินได้" : "Failed to initiate checkout process.");
      }
    } catch (err: any) {
      console.error("Checkout failed", err);
      alert(err.response?.data?.detail || "Checkout session failed.");
    } finally {
      setCheckingOut(false);
    }
  };

  const handleLeadCapture = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!product) return;
    if (!leadEmail.trim()) {
      alert(locale === "th" ? "กรุณากรอกอีเมลของคุณ" : "Please enter your email.");
      return;
    }

    try {
      setSubmittingLead(true);
      setLeadSuccessMsg("");
      const res = await funnelApi.captureLead(productSlug, {
        organization_id: orgId,
        email: leadEmail.trim(),
        name: leadName.trim() || undefined,
        source: "sales_page",
      });
      setLeadSuccessMsg(locale === "th" ? "สำเร็จ! ตรวจสอบอีเมลของคุณเพื่อรับตัวอย่างฟรี" : "You're in! Check your email for the free sample.");
      if (res.delivery_url) {
        setLeadDownloadUrl(res.delivery_url);
      }
    } catch (err: any) {
      console.error("Lead capture failed", err);
      setErrorMsg(err.response?.data?.detail || "Failed to submit.");
    } finally {
      setSubmittingLead(false);
    }
  };

  const cp = catalogProduct;
  const productName = cp?.name || product?.name || "Product";
  const productDesc = cp?.shortDescription || product?.short_description || "";
  const fullDesc = cp?.description || product?.sales_page_content || "";
  const price = cp?.priceAmount || parseFloat(product?.price_amount?.toString() || "0");
  const currency = cp?.currency || product?.currency || "USD";
  const features = cp?.features || [];
  const testimonials = cp?.testimonials || [];
  const deliverables = cp?.deliverables || [];
  const guaranteeDays = cp?.guaranteeDays || 30;
  const salesCount = cp?.salesCount || 0;
  const rating = cp?.rating || 4.8;
  const reviewCount = cp?.reviewCount || 0;

  const faqs = [
    { q: locale === "th" ? "หลังซื้อแล้วจะได้รับอะไรบ้าง?" : "What do I get after purchase?", a: locale === "th" ? "คุณจะได้รับสินค้าดิจิทัลทันที รวมถึงเทมเพลต คู่มือ และทรัพยากรทั้งหมดในสินค้านี้ ทุกอย่างส่งผ่านลิงก์ดาวน์โหลดปลอดภัยไปยังอีเมลของคุณทันที" : "You receive instant access to all digital files, templates, and resources included in this product. Everything is delivered via a secure download link sent to your email immediately." },
    { q: locale === "th" ? "การรับประกันคืนเงินทำงานอย่างไร?" : "How does the money-back guarantee work?", a: locale === "th" ? `หากคุณไม่พอใจภายใน ${guaranteeDays} วัน อีเมลมาหาเรา เราจะคืนเงินเต็มจำนวน ไม่มีคำถาม` : `If you're not satisfied within ${guaranteeDays} days, email us and we'll issue a full refund. No questions asked.` },
    { q: locale === "th" ? "สามารถใช้ในเชิงพาณิชย์ได้หรือไม่?" : "Can I use this commercially?", a: locale === "th" ? "ได้! ทุกสินค้ามีลิขสิทธิ์การใช้งานเชิงพาณิชย์ คุณสามารถใช้ในธุรกิจ ทำงานให้ลูกค้า และดัดแปลงตามต้องการ" : "Yes! All products come with a commercial license. You can use them in your business, for client work, and modify them as needed." },
    { q: locale === "th" ? "ได้รับอัปเดตฟรีหรือไม่?" : "Do I get free updates?", a: locale === "th" ? "ใช่! ทุกสินค้ารวมอัปเดตตลอดชีพ เมื่อเราปรับปรุงสินค้า คุณจะได้รับเวอร์ชันอัปเดตโดยไม่มีค่าใช้จ่ายเพิ่ม" : "Yes! All products include lifetime updates. When we improve the product, you'll receive the updated version at no extra cost." },
  ];

  if (loading) {
    return <SkeletonProductDetail />;
  }

  if (errorMsg || !product) {
    return (
      <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center text-slate-400 p-6">
        <div className="w-16 h-16 bg-rose-500/10 border border-rose-500/20 text-rose-400 rounded-3xl flex items-center justify-center mb-6">
          <AlertTriangle size={32} />
        </div>
        <h2 className="text-2xl font-bold text-slate-100">{locale === "th" ? "ไม่พบสินค้า" : "Product Unavailable"}</h2>
        <p className="text-sm text-slate-500 text-center max-w-md mt-2">{errorMsg || (locale === "th" ? "สินค้านี้ไม่พร้อมใช้งานในขณะนี้" : "This product is currently unavailable.")}</p>
        <Link to="/store" className={`mt-6 px-6 py-3 bg-indigo-500 hover:bg-indigo-600 text-white font-semibold rounded-xl transition-all duration-200 ${ANIMATIONS.buttonPress}`}>
          {locale === "th" ? "ดูร้านค้า" : "Browse Store"}
        </Link>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-indigo-500 selection:text-white overflow-x-hidden">
      {/* SEO Structured Data */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            "@context": "https://schema.org",
            "@type": "Product",
            name: productName,
            description: productDesc,
            image: cp?.coverImageUrl || product?.cover_image_url,
            brand: { "@type": "Brand", name: "Ai Factory" },
            offers: {
              "@type": "Offer",
              price: price,
              priceCurrency: currency,
              availability: "https://schema.org/InStock",
              seller: { "@type": "Organization", name: "Ai Factory" },
            },
            aggregateRating: {
              "@type": "AggregateRating",
              ratingValue: rating,
              reviewCount: reviewCount,
            },
          }),
        }}
      />

      {/* Background */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] rounded-full bg-indigo-500/8 blur-[120px]" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] rounded-full bg-cyan-500/6 blur-[120px]" />
      </div>

      {/* Sticky Header */}
      <div className="fixed top-0 left-0 right-0 z-50 border-b border-slate-800/50 bg-slate-950/90 backdrop-blur-xl">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <Link to="/store" className={`flex items-center gap-2 text-slate-400 hover:text-white text-sm transition-colors duration-200 ${ANIMATIONS.underlineHover}`}>
            <ArrowLeft size={16} />
            <span className="hidden sm:inline">{t("product.backToStore")}</span>
          </Link>
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-cyan-400 flex items-center justify-center font-mono font-bold text-[10px] text-slate-950">AI</div>
            <span className="font-display font-bold text-sm text-white">{t("brand.name")}</span>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={toggle} className={`text-xs px-2 py-1 rounded-lg border transition-all duration-200 ${ANIMATIONS.buttonPress} ${locale === "th" ? "bg-indigo-500/10 border-indigo-500/30 text-indigo-300" : "bg-slate-800/50 border-slate-700/50 text-slate-400 hover:text-white"}`}>
              {t("lang.switch")}
            </button>
            <span className="hidden sm:inline text-xs text-slate-400 font-mono">{formatPrice(price, currency)}</span>
            <button
              onClick={() => document.getElementById("checkout-section")?.scrollIntoView({ behavior: "smooth" })}
              className={`px-4 py-1.5 bg-indigo-500 hover:bg-indigo-600 text-white text-xs font-semibold rounded-xl transition-all duration-200 ${ANIMATIONS.buttonPress}`}
            >
              {t("product.buyNow")}
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 pt-20 pb-16 relative z-10 space-y-16">
        {/* Hero Section */}
        <ScrollReveal>
        <section className="grid grid-cols-1 lg:grid-cols-12 gap-10 items-start">
          {/* Left: Pitch */}
          <div className="lg:col-span-7 space-y-6 pt-4">
            {/* Category Badge */}
            <div className="flex items-center gap-2 flex-wrap">
              {cp && (
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
                  {CATEGORY_META[cp.category].icon} {t(`cat.${cp.category}`)}
                </span>
              )}
              {cp?.badge && (
                <span className="px-2.5 py-1 bg-amber-500/10 text-amber-300 border border-amber-500/20 rounded-full text-[10px] font-bold uppercase tracking-wider">
                  {cp.badge}
                </span>
              )}
              <span className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">
                {cp?.difficulty || (locale === "th" ? "ทุกระดับ" : "All Levels")}
              </span>
            </div>

            {/* Title */}
            <h1 className="text-3xl sm:text-4xl md:text-5xl font-display font-extrabold tracking-tight leading-[1.1]">
              <span className="bg-gradient-to-r from-white via-white to-slate-300 bg-clip-text text-transparent">
                {productName}
              </span>
            </h1>

            {/* Subtitle */}
            <p className="text-lg text-slate-300 font-medium leading-relaxed max-w-2xl">
              {productDesc}
            </p>

            {/* Social Proof */}
            <div className="flex flex-wrap items-center gap-4 text-sm">
              <div className="flex items-center gap-1.5">
                {[...Array(5)].map((_, i) => (
                  <Star key={i} size={14} className="fill-amber-400 text-amber-400" />
                ))}
                <span className="text-slate-300 font-semibold ml-1">{rating}</span>
                <span className="text-slate-500">({reviewCount.toLocaleString()} {locale === "th" ? "รีวิว" : "reviews"})</span>
              </div>
              <span className="text-slate-600">·</span>
              <div className="flex items-center gap-1.5 text-slate-400">
                <Users size={14} />
                <span>{formatSalesCount(salesCount)} {locale === "th" ? "ขายแล้ว" : "sold"}</span>
              </div>
              {cp && (
                <>
                  <span className="text-slate-600">·</span>
                  <span className="text-slate-400">{locale === "th" ? "อัปเดต" : "Updated"} {new Date(cp.lastUpdated).toLocaleDateString(locale === "th" ? "th-TH" : "en-US", { month: "short", year: "numeric" })}</span>
                </>
              )}
            </div>

            {/* Features */}
            {features.length > 0 && (
              <div className="space-y-3 pt-2">
                <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider">{t("product.whatsIncluded")}</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  {features.map((f, i) => (
                    <div key={i} className="flex items-start gap-2.5 text-sm text-slate-400">
                      <Check size={16} className="text-emerald-400 mt-0.5 shrink-0" />
                      <span>{f}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Full Description */}
            {fullDesc && (
              <div className="prose prose-invert max-w-none pt-4 text-slate-400 space-y-4 text-sm leading-relaxed">
                {cp ? (
                  <p>{cp.description}</p>
                ) : (
                  <div dangerouslySetInnerHTML={{ __html: fullDesc }} />
                )}
              </div>
            )}
          </div>

          {/* Right: Checkout Card */}
          <div id="checkout-section" className="lg:col-span-5 space-y-5 sticky top-20">
            {/* Purchase Card */}
            <div className="bg-slate-900/40 border border-slate-800 rounded-3xl p-6 shadow-2xl backdrop-blur-xl space-y-5 relative overflow-hidden">
              <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-bl from-indigo-500/10 to-transparent blur-xl pointer-events-none" />

              {/* Price */}
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider">{t("product.premiumAccess")}</span>
                  {cp?.badge && (
                    <span className="px-2 py-0.5 bg-emerald-500/10 text-emerald-400 text-[10px] font-bold rounded-full border border-emerald-500/20">
                      {cp.badge}
                    </span>
                  )}
                </div>
                <div className="flex items-baseline gap-2 mt-2">
                  <span className="text-4xl font-extrabold text-white">{formatPrice(price, currency)}</span>
                  <span className="text-sm text-slate-500 line-through">{formatPrice(Math.round(price * 1.5), currency)}</span>
                </div>
                <p className="text-[10px] text-slate-500 mt-1">{t("product.oneTime")} · {guaranteeDays}-{locale === "th" ? "วันรับประกัน" : "day guarantee"}</p>
              </div>

              {/* Checkout Form */}
              <form onSubmit={handleCheckout} className="space-y-3">
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                    <Mail size={12} className="text-indigo-400" />
                    {t("product.deliveryEmail")}
                  </label>
                  <input
                    type="email"
                    required
                    placeholder={locale === "th" ? "คุณ@example.com" : "you@example.com"}
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 focus:border-indigo-500 text-slate-200 px-4 py-3 rounded-xl text-sm outline-none transition-colors duration-200"
                  />
                </div>

                <button
                  type="submit"
                  disabled={checkingOut}
                  className={`w-full py-4 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 disabled:opacity-50 text-white font-bold rounded-xl shadow-glow-md transition-all duration-200 flex items-center justify-center gap-2 group text-sm ${ANIMATIONS.buttonPress} ${ANIMATIONS.buttonHover}`}
                >
                  {checkingOut ? (
                    <span className="flex items-center gap-2">
                      <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      {t("product.connecting")}
                    </span>
                  ) : (
                    <>
                      {t("product.unlockAccess")}
                      <ArrowRight size={16} className="group-hover:translate-x-0.5 transition-transform" />
                    </>
                  )}
                </button>
              </form>

              {/* Trust Signals */}
              <div className="space-y-2.5 text-xs text-slate-500">
                {[
                  { icon: CheckCircle, text: t("product.instantAccess") },
                  { icon: ShieldCheck, text: t("product.stripeEncrypted") },
                  { icon: Award, text: `${guaranteeDays}-${locale === "th" ? "วันรับประกันคืนเงิน" : "day money-back guarantee"}` },
                  { icon: Lock, text: t("product.secureEncrypted") },
                ].map(({ icon: Icon, text }) => (
                  <div key={text} className="flex items-center gap-2">
                    <Icon size={14} className="text-emerald-500" />
                    <span>{text}</span>
                  </div>
                ))}
              </div>

              {/* Urgency */}
              <div className="p-3 bg-amber-500/5 border border-amber-500/10 rounded-xl text-center">
                <div className="flex items-center justify-center gap-1.5 text-xs text-amber-400 font-semibold">
                  <Clock size={12} />
                  {t("product.limitedOffer")}
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
                <div className="p-2 bg-indigo-500/10 rounded-xl text-indigo-400">
                  <Gift size={16} />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-white">{t("product.freeSample")}</h4>
                  <p className="text-[10px] text-slate-500">{t("product.freeSampleDesc")}</p>
                </div>
              </div>

              {leadSuccessMsg ? (
                <div className="p-3 bg-emerald-500/5 border border-emerald-500/10 text-emerald-400 rounded-xl text-xs space-y-2">
                  <p className="font-semibold">{leadSuccessMsg}</p>
                  {leadDownloadUrl && (
                    <a href={leadDownloadUrl} className={`inline-flex items-center gap-1.5 font-bold text-indigo-400 hover:text-indigo-300 underline text-xs ${ANIMATIONS.underlineHover}`}>
                      <Download size={12} /> {locale === "th" ? "ดาวน์โหลดตัวอย่างฟรี" : "Download Free Sample"}
                    </a>
                  )}
                </div>
              ) : (
                <form onSubmit={handleLeadCapture} className="space-y-2">
                  <div className="grid grid-cols-2 gap-2">
                    <input type="text" placeholder={locale === "th" ? "ชื่อ" : "Name"} value={leadName} onChange={(e) => setLeadName(e.target.value)}
                      className="bg-slate-950 border border-slate-800 text-slate-300 px-3 py-2 rounded-xl text-xs outline-none focus:border-indigo-500 transition-colors duration-200" />
                    <input type="email" required placeholder={locale === "th" ? "อีเมล" : "Email"} value={leadEmail} onChange={(e) => setLeadEmail(e.target.value)}
                      className="bg-slate-950 border border-slate-800 text-slate-300 px-3 py-2 rounded-xl text-xs outline-none focus:border-indigo-500 transition-colors duration-200" />
                  </div>
                  <button type="submit" disabled={submittingLead}
                    className={`w-full py-2 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-200 text-xs font-semibold rounded-xl transition-all duration-200 ${ANIMATIONS.buttonPress}`}>
                    {submittingLead ? (locale === "th" ? "กำลังส่ง..." : "Sending...") : t("product.getFreeSample")}
                  </button>
                </form>
              )}
            </div>
          </div>
        </section>
        </ScrollReveal>

        {/* Testimonials */}
        {testimonials.length > 0 && (
          <ScrollReveal delay={100}>
          <section>
            <h2 className="text-2xl font-display font-extrabold text-white mb-6">{t("product.customersSay")}</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {testimonials.map((tItem, i) => (
                <div key={i} className={`p-5 bg-slate-900/40 border border-slate-800/60 rounded-2xl space-y-3 ${ANIMATIONS.cardHover}`} style={staggerDelay(i)}>
                  <div className="flex gap-0.5">
                    {[...Array(5)].map((_, j) => (
                      <Star key={j} size={12} className="fill-amber-400 text-amber-400" />
                    ))}
                  </div>
                  <p className="text-sm text-slate-300 leading-relaxed">"{tItem.text}"</p>
                  <div className="flex items-center gap-2.5 pt-1">
                    <div className="w-8 h-8 rounded-full bg-indigo-500 flex items-center justify-center text-white text-[10px] font-bold">{tItem.avatar}</div>
                    <div>
                      <div className="text-xs font-semibold text-white">{tItem.name}</div>
                      <div className="text-[10px] text-slate-500">{tItem.role}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>
          </ScrollReveal>
        )}

        {/* What You Get */}
        {deliverables.length > 0 && (
          <ScrollReveal delay={100}>
          <section>
            <h2 className="text-2xl font-display font-extrabold text-white mb-6">{t("product.youllReceive")}</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {deliverables.map((d, i) => (
                <div key={i} className={`flex items-center gap-3 p-4 bg-slate-900/30 border border-slate-800/50 rounded-xl ${ANIMATIONS.cardHover}`} style={staggerDelay(i)}>
                  <div className="w-8 h-8 rounded-lg bg-indigo-500/10 flex items-center justify-center text-indigo-400 shrink-0">
                    <Download size={14} />
                  </div>
                  <span className="text-sm text-slate-300">{d}</span>
                </div>
              ))}
            </div>
          </section>
          </ScrollReveal>
        )}

        {/* FAQ */}
        <ScrollReveal delay={100}>
        <section>
          <h2 className="text-2xl font-display font-extrabold text-white mb-6">{t("product.faqTitle")}</h2>
          <div className="space-y-3 max-w-3xl">
            {faqs.map((faq, i) => (
              <div key={i} className="border border-slate-800/60 rounded-2xl overflow-hidden">
                <button onClick={() => setOpenFaq(openFaq === i ? null : i)}
                  aria-expanded={openFaq === i}
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
              <h2 className="text-2xl md:text-3xl font-display font-extrabold text-white">
                {t("product.readyToStart")}
              </h2>
              <p className="text-slate-400 max-w-md mx-auto text-sm">
                {formatSalesCount(salesCount)} {t("product.joinCustomers")}
              </p>
              <button
                onClick={() => document.getElementById("checkout-section")?.scrollIntoView({ behavior: "smooth" })}
                className={`inline-flex items-center gap-2 px-8 py-4 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white font-bold rounded-2xl shadow-glow-md transition-all duration-200 ${ANIMATIONS.buttonPress} ${ANIMATIONS.buttonHover}`}
              >
                {t("product.buyNow")} — {formatPrice(price, currency)}
                <ArrowRight size={18} />
              </button>
              <div className="flex items-center justify-center gap-1.5 text-xs text-slate-500">
                <ShieldCheck size={12} className="text-emerald-500/60" />
                {guaranteeDays}-{locale === "th" ? "วันรับประกันคืนเงิน" : "day money-back guarantee"} · {locale === "th" ? "ส่งมอบทันที" : "Instant delivery"}
              </div>
            </div>
          </div>
        </section>
        </ScrollReveal>
      </div>
    </div>
  );
}

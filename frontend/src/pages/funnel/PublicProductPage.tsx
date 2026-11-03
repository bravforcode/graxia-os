import { useCallback, useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  CheckCircle, ArrowRight, Mail, ShieldCheck, Download,
  AlertTriangle, Gift, Star, ChevronDown, Check, Users,
  Lock, ArrowLeft, CreditCard,
} from "lucide-react";
import { useLang } from "../../i18n/LanguageContext";
import { PRODUCTS, CATEGORY_META, formatPrice, formatSalesCount, getLocalizedName, getLocalizedShortDescription, getLocalizedDescription, type ProductCatalogItem } from "../../data/products";
import { getLeadMagnet } from "../../data/organic";
import { funnelApi, type DigitalProduct } from "../../api/funnel";
import { ANIMATIONS, staggerDelay } from "../../lib/animations";
import { ScrollReveal } from "../../components/ui/ScrollReveal";
import { SkeletonProductDetail } from "../../components/ui/Skeleton";
import { getAttributionEventFields } from "../../lib/attribution";
import { siteUrl } from "../../lib/site";

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
  const [marketingConsent, setMarketingConsent] = useState(false);
  const [submittingLead, setSubmittingLead] = useState(false);
  const [leadSuccessMsg, setLeadSuccessMsg] = useState("");
  const [leadDownloadUrl, setLeadDownloadUrl] = useState("");

  // FAQ accordion
  const [openFaq, setOpenFaq] = useState<number | null>(null);


  const orgId = organization_id || "";
  const productSlug = slug || "";

  // Match catalog product
  useEffect(() => {
    if (productSlug) {
      const match = PRODUCTS.find((p) => p.slug === productSlug);
      setCatalogProduct(match || null);
    }
  }, [productSlug]);

  const loadProduct = useCallback(async () => {
    try {
      setLoading(true);
      setErrorMsg("");
      const data = await funnelApi.getPublicProduct(orgId, productSlug);
      setProduct(data);

      await funnelApi.logPublicEvent({
        organization_id: orgId,
        event_type: "page_view",
        product_id: data.id,
        ...getAttributionEventFields({ content_id: data.id, path: window.location.pathname }),
        idempotency_key: `page_view:${getAttributionEventFields().session_id}:${data.id}`,
      }).catch(() => {});
    } catch (err: unknown) {
      console.error("Failed to retrieve public product", err);
      setErrorMsg(err instanceof Error ? err.message : "Product not found or currently unavailable.");
    } finally {
      setLoading(false);
    }
  }, [orgId, productSlug]);

  useEffect(() => {
    if (orgId && productSlug) {
      void loadProduct();
    }
  }, [loadProduct, orgId, productSlug]);

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
        ...getAttributionEventFields({ content_id: product.id, cta: "checkout" }),
        idempotency_key: `checkout_start:${getAttributionEventFields().session_id}:${product.id}`,
      }).catch(() => {});

      const successUrl = siteUrl("/checkout/success?session_id={CHECKOUT_SESSION_ID}");
      const cancelUrl = siteUrl(`/store/${productSlug}`);
      const checkoutAttribution = getAttributionEventFields({ content_id: product.id, cta: "checkout" });

      const checkout = await funnelApi.createPublicCheckoutSession(product.id, {
        organization_id: orgId,
        customer_email: email.trim(),
        success_url: successUrl,
        cancel_url: cancelUrl,
        metadata: {
          ...checkoutAttribution,
          ...(checkoutAttribution.metadata_json || {}),
        },
      });

      if (checkout.checkout_url) {
        window.location.href = checkout.checkout_url;
      } else {
        alert(locale === "th" ? "ไม่สามารถเริ่มกระบวนการชำระเงินได้" : "Failed to initiate checkout process.");
      }
    } catch (err: unknown) {
      console.error("Checkout failed", err);
      alert(err instanceof Error ? err.message : "Checkout session failed.");
    } finally {
      setCheckingOut(false);
    }
  };

  const handleLeadCapture = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!product || !leadMagnet) return;
    if (!leadEmail.trim()) {
      alert(locale === "th" ? "กรุณากรอกอีเมลของคุณ" : "Please enter your email.");
      return;
    }

    try {
      setSubmittingLead(true);
      setLeadSuccessMsg("");
      const attribution = getAttributionEventFields({ content_id: product.id, cta: "lead_magnet" });
      const res = await funnelApi.captureLead(leadMagnet.slug, {
        organization_id: orgId,
        email: leadEmail.trim(),
        name: leadName.trim() || undefined,
        marketing_consent: marketingConsent,
        consent_version: marketingConsent ? "organic-v1" : undefined,
        session_id: attribution.session_id,
        source: attribution.source,
        medium: attribution.medium,
        campaign: attribution.campaign,
        referrer: attribution.referrer,
        referral_code: attribution.referral_code,
      });
      setLeadSuccessMsg(locale === "th" ? "สำเร็จ! ตรวจสอบอีเมลของคุณเพื่อรับตัวอย่างฟรี" : "You're in! Check your email for the free sample.");
      if (res.delivery_url) {
        setLeadDownloadUrl(res.delivery_url);
      }
    } catch (err: unknown) {
      console.error("Lead capture failed", err);
      setErrorMsg(err instanceof Error ? err.message : "Failed to submit.");
    } finally {
      setSubmittingLead(false);
    }
  };

  const cp = catalogProduct;
  const leadMagnet = cp ? getLeadMagnet(cp.slug) : undefined;
  const productName = cp ? getLocalizedName(cp, locale) : product?.name || "Product";
  const productDesc = cp ? getLocalizedShortDescription(cp, locale) : product?.short_description || "";
  const fullDesc = cp ? getLocalizedDescription(cp, locale) : product?.sales_page_content || "";
  const price = cp?.priceAmount || parseFloat(product?.price_amount?.toString() || "0");
  const currency = cp?.currency || product?.currency || "USD";
  const features = cp?.features || [];
  const testimonials = cp?.testimonials || [];
  const deliverables = cp?.deliverables || [];
  const salesCount = cp?.salesCount || 0;
  const rating = cp?.rating || 0;
  const reviewCount = cp?.reviewCount || 0;

  const faqs = [
    { q: locale === "th" ? "หลังซื้อแล้วจะได้รับอะไรบ้าง?" : "What do I get after purchase?", a: locale === "th" ? "คุณจะได้รับไฟล์และสิทธิ์ตามที่ระบุในหน้าสินค้า หลัง event การซื้อได้รับการยืนยันและ delivery asset ถูกตั้งค่าไว้" : "You receive the files and access described on this product page after the purchase event is verified and a delivery asset is configured." },
    { q: locale === "th" ? "ดูเงื่อนไขคืนเงินได้ที่ไหน?" : "Where are refund terms shown?", a: locale === "th" ? "เงื่อนไขคืนเงินจะแสดงเมื่อมีการตั้งค่าไว้สำหรับสินค้านี้ อย่าสมมติระยะเวลาที่ไม่ได้แสดงบนหน้า" : "Refund terms are shown when configured for this product. Do not assume a window that is not displayed on the page." },
    { q: locale === "th" ? "สามารถใช้ในเชิงพาณิชย์ได้หรือไม่?" : "Can I use this commercially?", a: locale === "th" ? "ตรวจ license และเงื่อนไขการใช้งานของสินค้านี้ก่อนนำไปใช้เชิงพาณิชย์หรือทำงานให้ลูกค้า" : "Review this product's license and usage terms before commercial or client work." },
    { q: locale === "th" ? "ได้รับอัปเดตหรือไม่?" : "Do I get updates?", a: locale === "th" ? "เงื่อนไขอัปเดตต่างกันตามสินค้า จะแสดงเมื่อมีการตั้งค่าและมีหลักฐานปัจจุบัน" : "Update terms vary by product and are shown when configured with current evidence." },
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
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-indigo-500 selection:text-white overflow-x-clip">
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
            brand: { "@type": "Brand", name: "Graxia" },
            offers: {
              "@type": "Offer",
              price: price,
              priceCurrency: currency,
              availability: "https://schema.org/InStock",
              seller: { "@type": "Organization", name: "Graxia", url: siteUrl() },
            },
            ...(reviewCount > 0 && rating > 0 ? {
              aggregateRating: {
                "@type": "AggregateRating",
                ratingValue: rating,
                reviewCount: reviewCount,
              },
            } : {}),
          }),
        }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            "@context": "https://schema.org",
            "@type": "FAQPage",
            mainEntity: faqs.map((faq) => ({
              "@type": "Question",
              name: faq.q,
              acceptedAnswer: { "@type": "Answer", text: faq.a },
            })),
          }),
        }}
      />

      {/* Background */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] rounded-full bg-indigo-500/8 blur-[120px]" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] rounded-full bg-cyan-500/6 blur-[120px]" />
      </div>

      {/* Header — lyra floating pill navbar (consistent with store) */}
      <div className="sticky top-4 z-50 flex justify-center px-4">
        <div className="pill-nav w-full max-w-5xl flex h-[56px] items-center justify-between px-5">
          <Link to="/store" className={`flex items-center gap-2 text-slate-400 hover:text-slate-100 text-sm transition-colors duration-200 ${ANIMATIONS.underlineHover}`}>
            <ArrowLeft size={16} />
            <span className="hidden sm:inline">{t("product.backToStore")}</span>
          </Link>
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-cyan-400 flex items-center justify-center font-mono font-bold text-[11px] text-slate-950">AI</div>
            <span className="font-serif font-bold text-sm text-slate-100">{t("brand.name")}</span>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={toggle} className={`text-xs px-2 py-1 rounded-lg border transition-all duration-200 ${ANIMATIONS.buttonPress} ${locale === "th" ? "bg-indigo-500/10 border-indigo-500/30 text-indigo-300" : "bg-slate-800/50 border-slate-700/50 text-slate-400 hover:text-slate-100"}`}>
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
                <span className="px-2.5 py-1 bg-amber-500/10 text-amber-300 border border-amber-500/20 rounded-full text-[11px] font-bold uppercase tracking-wider">
                  {cp.badge}
                </span>
              )}
              <span className="text-[11px] text-slate-500 uppercase tracking-wider font-semibold">
                {cp?.difficulty || (locale === "th" ? "ทุกระดับ" : "All Levels")}
              </span>
            </div>

            {/* Title */}
            <h1 className="text-3xl sm:text-4xl md:text-5xl font-serif font-medium tracking-tight leading-[1.1]">
              <span className="bg-gradient-to-r from-indigo-400 via-purple-400 to-cyan-400 bg-clip-text text-transparent">
                {productName}
              </span>
            </h1>

            {/* Subtitle */}
            <p className="text-lg text-slate-300 font-medium leading-relaxed max-w-2xl">
              {productDesc}
            </p>

            {/* Social proof appears only when current evidence exists. */}
            {(reviewCount > 0 || salesCount > 0) && <div className="flex flex-wrap items-center gap-4 text-sm">
              {reviewCount > 0 && <div className="flex items-center gap-1.5">
                {[...Array(5)].map((_, i) => (
                  <Star key={i} size={14} className="fill-amber-400 text-amber-400" />
                ))}
                <span className="text-slate-300 font-semibold ms-1">{rating}</span>
                <span className="text-slate-500">({reviewCount.toLocaleString()} {locale === "th" ? "รีวิว" : "reviews"})</span>
              </div>}
              {reviewCount > 0 && salesCount > 0 && <span className="text-slate-600">·</span>}
              {salesCount > 0 && <div className="flex items-center gap-1.5 text-slate-400">
                <Users size={14} />
                <span>{formatSalesCount(salesCount)} {locale === "th" ? "ขายแล้ว" : "sold"}</span>
              </div>}
              {cp && (
                <>
                  <span className="text-slate-600">·</span>
                  <span className="text-slate-400">{locale === "th" ? "อัปเดต" : "Updated"} {new Date(cp.lastUpdated).toLocaleDateString(locale === "th" ? "th-TH" : "en-US", { month: "short", year: "numeric" })}</span>
                </>
              )}
            </div>}

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
            <div className="edge-light bg-slate-900/40 border border-white/[0.08] rounded-3xl p-6 shadow-2xl backdrop-blur-xl space-y-5 relative overflow-hidden">
              <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-bl from-indigo-500/10 to-transparent blur-xl pointer-events-none" />

              {/* Price */}
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider">{t("product.premiumAccess")}</span>
                  {cp?.badge && (
                    <span className="px-2 py-0.5 bg-emerald-500/10 text-emerald-400 text-[11px] font-bold rounded-full border border-emerald-500/20">
                      {cp.badge}
                    </span>
                  )}
                </div>
                <div className="flex items-baseline gap-2 mt-2">
                  <span className="text-4xl font-extrabold text-white">{formatPrice(price, currency)}</span>
                </div>
                <p className="text-[11px] text-slate-500 mt-1">{t("product.oneTime")}</p>
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
                  className={`w-full py-4 bg-secondary hover:bg-secondary/80 disabled:opacity-50 text-white font-bold rounded-xl shadow-lyra border border-white/[0.12] transition-all ease-out flex items-center justify-center gap-2 group text-sm active:scale-95 ${ANIMATIONS.buttonPress}`}
                >
                  {checkingOut ? (
                    <span className="relative z-10 flex items-center gap-2">
                      <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      {t("product.connecting")}
                    </span>
                  ) : (
                    <span className="relative z-10 flex items-center gap-2">
                      {t("product.unlockAccess")}
                      <ArrowRight size={16} className="group-hover:translate-x-0.5 transition-transform" />
                    </span>
                  )}
                </button>
              <p className="text-[11px] text-slate-500">{t("store.consent")}</p>
              </form>

              {/* Trust Signals */}
              <div className="space-y-2.5 text-xs text-slate-500">
                {[
                  { icon: CheckCircle, text: t("product.instantAccess") },
                  { icon: ShieldCheck, text: t("product.stripeEncrypted") },
                  { icon: Lock, text: t("product.secureEncrypted") },
                  { icon: CreditCard, text: t("store.promptpay") },
                ].map(({ icon: Icon, text }) => (
                  <div key={text} className="flex items-center gap-2">
                    <Icon size={14} className="text-emerald-500" />
                    <span>{text}</span>
                  </div>
                ))}
              </div>

            </div>

            {/* Lead Magnet */}
            {leadMagnet && <div className="bg-slate-900/20 border border-slate-800/60 rounded-3xl p-5 shadow-xl backdrop-blur-xl space-y-3">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-indigo-500/10 rounded-xl text-indigo-400">
                  <Gift size={16} />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-white">{t("product.freeSample")}</h4>
                  <p className="text-[11px] text-slate-500">{t("product.freeSampleDesc")}</p>
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
                    <input type="text" aria-label={t("store.name")} placeholder={locale === "th" ? "ชื่อ" : "Name"} value={leadName} onChange={(e) => setLeadName(e.target.value)}
                      className="bg-slate-950 border border-slate-800 text-slate-300 px-3 py-2 rounded-xl text-xs outline-none focus:border-indigo-500 transition-colors duration-200" />
                    <input type="email" required aria-label={t("auth.email")} placeholder={locale === "th" ? "อีเมล" : "Email"} value={leadEmail} onChange={(e) => setLeadEmail(e.target.value)}
                      className="bg-slate-950 border border-slate-800 text-slate-300 px-3 py-2 rounded-xl text-xs outline-none focus:border-indigo-500 transition-colors duration-200" />
                  </div>
                  <label className="flex items-start gap-2 text-[11px] text-slate-500">
                    <input
                      type="checkbox"
                      checked={marketingConsent}
                      onChange={(e) => setMarketingConsent(e.target.checked)}
                      className="mt-0.5 accent-indigo-500"
                    />
                    <span>{locale === "th" ? "ยินยอมรับข่าวสารการตลาดทางอีเมล (ไม่เลือกก็รับไฟล์ฟรีได้)" : "I agree to marketing emails (optional; the free file is available without this)."}</span>
                  </label>
                  <button type="submit" disabled={submittingLead}
                    className={`w-full py-2 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-200 text-xs font-semibold rounded-xl transition-all duration-200 ${ANIMATIONS.buttonPress}`}>
                    {submittingLead ? (locale === "th" ? "กำลังส่ง..." : "Sending...") : t("product.getFreeSample")}
                  </button>
                </form>
              )}
            </div>}
          </div>
        </section>
        </ScrollReveal>

        {/* Testimonials */}
        {testimonials.length > 0 && (
          <ScrollReveal delay={100}>
          <section>
            <h2 className="text-2xl font-serif font-medium text-white mb-6">{t("product.customersSay")}</h2>
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
                    <div className="w-8 h-8 rounded-full bg-indigo-500 flex items-center justify-center text-white text-[11px] font-bold">{tItem.avatar}</div>
                    <div>
                      <div className="text-xs font-semibold text-white">{tItem.name}</div>
                      <div className="text-[11px] text-slate-500">{tItem.role}</div>
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
            <h2 className="text-2xl font-serif font-medium text-white mb-6">{t("product.youllReceive")}</h2>
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
          <h2 className="text-2xl font-serif font-medium text-white mb-6">{t("product.faqTitle")}</h2>
          <div className="space-y-3 max-w-3xl">
            {faqs.map((faq, i) => (
              <div key={i} className="border border-slate-800/60 rounded-2xl overflow-hidden">
                <button onClick={() => setOpenFaq(openFaq === i ? null : i)}
                  aria-expanded={openFaq === i}
                  className="w-full flex items-center justify-between p-5 text-start bg-slate-900/30 hover:bg-slate-900/50 transition-colors duration-200">
                  <span className="font-semibold text-sm text-white pr-4">{faq.q}</span>
                  <ChevronDown size={16} className={`text-slate-400 shrink-0 transition-transform duration-300 ${openFaq === i ? "rotate-180" : ""}`} />
                </button>
                <div className={`overflow-hidden transition-all duration-300 ease-out ${openFaq === i ? "max-h-[40rem] overflow-y-auto opacity-100" : "max-h-0 opacity-0"}`}>
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
              <h2 className="text-2xl md:text-3xl font-serif font-medium text-white">
                {t("product.readyToStart")}
              </h2>
              {salesCount > 0 && <p className="text-slate-400 max-w-md mx-auto text-sm">
                {formatSalesCount(salesCount)} {t("product.joinCustomers")}
              </p>}
              <button
                onClick={() => document.getElementById("checkout-section")?.scrollIntoView({ behavior: "smooth" })}
                className={`inline-flex items-center gap-2 px-8 py-4 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white font-bold rounded-2xl shadow-glow-md transition-all duration-200 ${ANIMATIONS.buttonPress} ${ANIMATIONS.buttonHover}`}
              >
                {t("product.buyNow")} — {formatPrice(price, currency)}
                <ArrowRight size={18} />
              </button>
              <div className="flex items-center justify-center gap-1.5 text-xs text-slate-500">
                <ShieldCheck size={12} className="text-emerald-500/60" />
                {t("store.trust2")}
              </div>
            </div>
          </div>
        </section>
        </ScrollReveal>
      </div>
    </div>
  );
}

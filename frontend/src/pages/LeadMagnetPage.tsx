import { FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowRight, CheckCircle, Download, Mail } from "lucide-react";
import { useLang } from "../i18n/LanguageContext";
import { funnelApi } from "../api/funnel";
import { STORE_ORG_ID, getProductBySlug } from "../data/products";
import { getLeadMagnet } from "../data/organic";
import { getAttributionEventFields } from "../lib/attribution";
import { siteUrl } from "../lib/site";

export default function LeadMagnetPage() {
  const { slug = "" } = useParams<{ slug: string }>();
  const { locale } = useLang();
  const definition = getLeadMagnet(slug);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [marketingConsent, setMarketingConsent] = useState(false);
  const [deliveryUrl, setDeliveryUrl] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!definition) return;
    document.title = `${locale === "th" ? definition.title.th : definition.title.en} | Graxia`;
    let link = document.querySelector<HTMLLinkElement>('link[rel="canonical"]');
    if (!link) {
      link = document.createElement("link");
      link.rel = "canonical";
      document.head.appendChild(link);
    }
    link.href = siteUrl(`/free/${definition.slug}`);
  }, [definition, locale]);

  if (!definition) {
    return (
      <main className="min-h-screen bg-slate-950 text-slate-100 grid place-items-center p-6">
        <div className="text-center"><h1 className="text-2xl font-bold">Lead magnet not found</h1><Link className="text-indigo-300 mt-4 inline-block" to="/store">Browse Graxia store</Link></div>
      </main>
    );
  }

  const title = locale === "th" ? definition.title.th : definition.title.en;
  const promise = locale === "th" ? definition.promise.th : definition.promise.en;
  const description = locale === "th" ? definition.description.th : definition.description.en;
  const targetProduct = getProductBySlug(definition.targetProductSlug);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const attribution = getAttributionEventFields({
        content_id: `lead-magnet:${definition.slug}`,
        cta: "lead_capture",
        channel: "organic",
      });
      const result = await funnelApi.captureLead(definition.slug, {
        organization_id: STORE_ORG_ID,
        email,
        name: name || undefined,
        marketing_consent: marketingConsent,
        consent_version: marketingConsent ? "organic-v1" : undefined,
        session_id: attribution.session_id,
        source: attribution.source,
        medium: attribution.medium,
        campaign: attribution.campaign,
        referrer: attribution.referrer,
        referral_code: attribution.referral_code,
      });
      setDeliveryUrl(result.delivery_url ?? null);
      setSubmitted(true);
    } catch (submissionError: unknown) {
      setError(submissionError instanceof Error ? submissionError.message : "Lead capture failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100 px-6 py-10">
      <div className="max-w-5xl mx-auto">
        <Link to="/" className="text-sm text-slate-400 hover:text-white">← Graxia</Link>
        <div className="grid lg:grid-cols-[1.1fr_0.9fr] gap-8 mt-12 items-start">
          <section>
            <p className="text-xs uppercase tracking-[0.18em] text-indigo-300">Free resource · evidence-aware</p>
            <h1 className="text-4xl md:text-6xl font-serif tracking-tight mt-4">{title}</h1>
            <p className="text-xl text-slate-300 mt-5 leading-8">{promise}</p>
            <p className="text-slate-400 mt-5 leading-7 max-w-2xl">{description}</p>
            <div className="mt-8 space-y-3">
              {definition.bullets.map((bullet) => (
                <div key={bullet.en} className="flex gap-3 text-sm text-slate-300"><CheckCircle size={18} className="text-emerald-400 shrink-0" /><span>{locale === "th" ? bullet.th : bullet.en}</span></div>
              ))}
            </div>
          </section>

          <section className="rounded-3xl border border-slate-800 bg-slate-900/70 p-6 shadow-2xl">
            {submitted ? (
              <div className="space-y-4">
                <Download className="text-emerald-400" size={28} />
                <h2 className="text-xl font-semibold">{locale === "th" ? "รับคำขอแล้ว" : "Request received"}</h2>
                <p className="text-sm leading-6 text-slate-400">{marketingConsent ? (locale === "th" ? "คุณยินยอมรับ nurture ตาม consent version organic-v1" : "You opted into nurture under consent version organic-v1.") : (locale === "th" ? "ส่งไฟล์ได้ แต่จะไม่เข้า nurture sequence เพราะยังไม่ได้ยินยอม marketing" : "The file can be delivered, but you will not enter nurture without marketing consent.")}</p>
                {deliveryUrl && <a className="inline-flex items-center gap-2 text-indigo-300" href={deliveryUrl}>Open delivery <ArrowRight size={16} /></a>}
                <Link className="inline-flex items-center gap-2 text-slate-300" to={`/store/${definition.targetProductSlug}`}>View related product <ArrowRight size={16} /></Link>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-4">
                <h2 className="text-xl font-semibold">{locale === "th" ? "รับไฟล์ฟรี" : "Get the free file"}</h2>
                <p className="text-sm text-slate-400">{locale === "th" ? "ไม่ต้องยินยอม marketing เพื่อรับไฟล์ และเปลี่ยนใจได้ทุกเมื่อ" : "Marketing consent is optional for delivery and can be withdrawn later."}</p>
                <label className="block text-sm text-slate-300">{locale === "th" ? "ชื่อ (ถ้ามี)" : "Name (optional)"}<input value={name} onChange={(event) => setName(event.target.value)} className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-3" /></label>
                <label className="block text-sm text-slate-300"><span className="flex items-center gap-2"><Mail size={15} />Email</span><input required type="email" value={email} onChange={(event) => setEmail(event.target.value)} className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-3" /></label>
                <label className="flex gap-3 text-xs leading-5 text-slate-400"><input type="checkbox" checked={marketingConsent} onChange={(event) => setMarketingConsent(event.target.checked)} className="mt-1" />{locale === "th" ? "ยินยอมรับ email nurture ที่เกี่ยวข้องกับ Graxia โดยใช้ consent version organic-v1" : "I consent to relevant Graxia email nurture under consent version organic-v1"}</label>
                {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
                <button disabled={submitting} className="w-full rounded-xl bg-indigo-500 px-4 py-3 font-semibold disabled:opacity-50">{submitting ? "..." : (locale === "th" ? "ส่งคำขอไฟล์" : "Send request")}</button>
              </form>
            )}
          </section>
        </div>
        {targetProduct && <p className="mt-10 text-sm text-slate-500">Related catalog item: <Link className="text-indigo-300" to={`/store/${targetProduct.slug}`}>{targetProduct.name}</Link></p>}
      </div>
    </main>
  );
}

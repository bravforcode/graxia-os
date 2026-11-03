import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowRight, BookOpen, CheckCircle } from "lucide-react";
import { useLang } from "../i18n/LanguageContext";
import { getLocalizedName, getProductBySlug } from "../data/products";
import { getLeadMagnet, getSeoCluster } from "../data/organic";
import { funnelApi, type PublicContentArticle } from "../api/funnel";
import { siteUrl } from "../lib/site";

export default function SeoClusterPage() {
  const { slug = "" } = useParams<{ slug: string }>();
  const { locale } = useLang();
  const cluster = getSeoCluster(slug);
  const [article, setArticle] = useState<PublicContentArticle | null>(null);
  const [articleLoaded, setArticleLoaded] = useState(false);

  useEffect(() => {
    let active = true;
    setArticleLoaded(false);
    void funnelApi.getPublishedArticle(slug, locale === "th" ? "th" : "en")
      .then((published) => {
        if (active) setArticle(published);
      })
      .catch(() => {
        if (active) setArticle(null);
      })
      .finally(() => {
        if (active) setArticleLoaded(true);
      });
    return () => {
      active = false;
    };
  }, [slug, locale]);

  useEffect(() => {
    if (!cluster && !article) return;
    const title = article
      ? (locale === "th" && article.title_th ? article.title_th : article.title)
      : (locale === "th" ? cluster!.title.th : cluster!.title.en);
    document.title = `${title} | Graxia`;
    let link = document.querySelector<HTMLLinkElement>('link[rel="canonical"]');
    if (!link) {
      link = document.createElement("link");
      link.rel = "canonical";
      document.head.appendChild(link);
    }
    link.href = siteUrl(`/guides/${slug}`);
  }, [article, cluster, locale, slug]);

  if (!cluster && !articleLoaded) {
    return <main className="min-h-screen bg-slate-950 text-slate-100 grid place-items-center p-6"><div>Loading guide...</div></main>;
  }
  if (!cluster && !article) {
    return <main className="min-h-screen bg-slate-950 text-slate-100 grid place-items-center p-6"><div><h1 className="text-2xl font-bold">Guide not found</h1><Link className="text-indigo-300 mt-4 inline-block" to="/">Back to Graxia</Link></div></main>;
  }

  const title = article
    ? (locale === "th" && article.title_th ? article.title_th : article.title)
    : (locale === "th" ? cluster!.title.th : cluster!.title.en);
  const description = article?.meta_description
    ?? (locale === "th" ? cluster!.description.th : cluster!.description.en);
  const intent = cluster
    ? (locale === "th" ? cluster.intent.th : cluster.intent.en)
    : "Published Graxia guide";
  const leadMagnet = cluster ? getLeadMagnet(cluster.leadMagnetSlug) : undefined;
  const products = cluster ? cluster.productSlugs.map(getProductBySlug).filter(Boolean) : [];
  const faqEntities = (cluster?.faqs ?? []).map((faq) => ({
    "@type": "Question",
    name: locale === "th" ? faq.question.th : faq.question.en,
    acceptedAnswer: { "@type": "Answer", text: locale === "th" ? faq.answer.th : faq.answer.en },
  }));

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100 px-6 py-10">
      <div className="max-w-5xl mx-auto">
        <Link to="/" className="text-sm text-slate-400 hover:text-white">← Graxia</Link>
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify({
          "@context": "https://schema.org",
          "@type": "Article",
          headline: title,
          description,
          url: siteUrl(`/guides/${slug}`),
          author: { "@type": "Organization", name: "Graxia", url: siteUrl() },
          mainEntity: { "@type": "FAQPage", mainEntity: faqEntities },
        }) }} />
        <header className="max-w-3xl mt-16">
          <p className="text-xs uppercase tracking-[0.18em] text-indigo-300 flex items-center gap-2"><BookOpen size={14} /> Organic guide</p>
          <h1 className="text-4xl md:text-6xl font-serif tracking-tight mt-4">{title}</h1>
          <p className="text-xl leading-8 text-slate-300 mt-5">{description}</p>
          <p className="text-sm text-slate-500 mt-4">{intent}</p>
        </header>

        {article && <article className="mt-12 max-w-3xl whitespace-pre-wrap leading-8 text-slate-200">{article.body}</article>}

        {cluster && <section className="grid md:grid-cols-2 gap-5 mt-12">
          {cluster.faqs.map((faq) => (
            <article key={faq.question.en} className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6">
              <h2 className="font-semibold">{locale === "th" ? faq.question.th : faq.question.en}</h2>
              <p className="text-sm leading-7 text-slate-400 mt-3">{locale === "th" ? faq.answer.th : faq.answer.en}</p>
            </article>
          ))}
        </section>}

        {leadMagnet && <section className="mt-10 rounded-3xl border border-indigo-500/30 bg-indigo-500/10 p-7 flex flex-wrap items-center justify-between gap-5">
          <div><p className="text-xs uppercase tracking-wider text-indigo-300">Free lead magnet</p><h2 className="text-xl font-semibold mt-2">{locale === "th" ? leadMagnet.title.th : leadMagnet.title.en}</h2><p className="text-sm text-slate-300 mt-2">{locale === "th" ? leadMagnet.promise.th : leadMagnet.promise.en}</p></div>
          <Link to={`/free/${leadMagnet.slug}`} className="inline-flex items-center gap-2 rounded-xl bg-indigo-500 px-4 py-3 font-semibold">Get the checklist <ArrowRight size={16} /></Link>
        </section>}

        <section className="mt-12">
          <h2 className="text-2xl font-semibold">{locale === "th" ? "สินค้าและ workflow ที่เกี่ยวข้อง" : "Related products and workflows"}</h2>
          <div className="grid md:grid-cols-3 gap-5 mt-5">
            {products.map((product) => product && <Link key={product.slug} to={`/store/${product.slug}`} className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 hover:border-indigo-400/50">
              <CheckCircle size={18} className="text-emerald-400" /><h3 className="font-semibold mt-4">{getLocalizedName(product, locale)}</h3><p className="text-sm text-slate-400 mt-2">{getLocalizedName(product, locale)}</p><span className="inline-flex items-center gap-2 text-sm text-indigo-300 mt-5">View item <ArrowRight size={14} /></span>
            </Link>)}
          </div>
        </section>
      </div>
    </main>
  );
}

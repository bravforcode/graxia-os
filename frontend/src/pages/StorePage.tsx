import { useState, useMemo, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  Search,
  Filter,
  Star,
  ArrowRight,
  X,
  TrendingUp,
  Sparkles,
  Shield,
  Globe,
} from "lucide-react";
import { useLang } from "../i18n/LanguageContext";
import {
  PRODUCTS,
  CATEGORY_META,
  formatPrice,
  formatSalesCount,
  type ProductCategory,
} from "../data/products";
import { ANIMATIONS, staggerDelay } from "../lib/animations";
import { SkeletonProductGrid } from "../components/ui/Skeleton";
import { ScrollReveal } from "../components/ui/ScrollReveal";

const ALL_CATEGORIES: ProductCategory[] = Object.keys(CATEGORY_META) as ProductCategory[];

export default function StorePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<ProductCategory | "all">(
    (searchParams.get("category") as ProductCategory | "all") || "all"
  );
  const [sortBy, setSortBy] = useState<"popular" | "newest" | "price-low" | "price-high" | "rating">("popular");
  const { locale, toggle, t } = useLang();
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => setIsLoading(false), 400);
    return () => clearTimeout(timer);
  }, []);

  const filteredProducts = useMemo(() => {
    let items = [...PRODUCTS];
    if (selectedCategory !== "all") items = items.filter((p) => p.category === selectedCategory);
    if (search.trim()) {
      const q = search.toLowerCase();
      items = items.filter(
        (p) => p.name.toLowerCase().includes(q) || p.shortDescription.toLowerCase().includes(q) || p.tags.some((t) => t.includes(q))
      );
    }
    switch (sortBy) {
      case "popular": items.sort((a, b) => b.salesCount - a.salesCount); break;
      case "newest": items.sort((a, b) => new Date(b.lastUpdated).getTime() - new Date(a.lastUpdated).getTime()); break;
      case "price-low": items.sort((a, b) => a.priceAmount - b.priceAmount); break;
      case "price-high": items.sort((a, b) => b.priceAmount - a.priceAmount); break;
      case "rating": items.sort((a, b) => b.rating - a.rating); break;
    }
    return items;
  }, [search, selectedCategory, sortBy]);

  const handleCategoryChange = (cat: ProductCategory | "all") => {
    setSelectedCategory(cat);
    if (cat === "all") { searchParams.delete("category"); } else { searchParams.set("category", cat); }
    setSearchParams(searchParams);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-indigo-500 selection:text-white">
      {/* SEO Structured Data */}
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify({
        "@context": "https://schema.org", "@type": "CollectionPage",
        name: "Ai Factory — Digital Products Marketplace",
        description: "Browse premium digital products: templates, courses, tools, and resources for creators, developers, and entrepreneurs.",
        url: "https://ai-factory-omega.vercel.app/store",
      }) }} />

      {/* Background */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[600px] rounded-full bg-indigo-500/5 blur-[150px]" />
        <div className="absolute bottom-0 right-0 w-[400px] h-[400px] rounded-full bg-cyan-500/4 blur-[120px]" />
      </div>

      {/* Header */}
      <div className="relative z-10 border-b border-slate-800/50 bg-slate-950/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 group">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-cyan-400 flex items-center justify-center font-mono font-bold text-sm text-slate-950 group-hover:scale-105 transition-transform duration-200">
              AI
            </div>
            <span className="font-display font-bold text-lg text-white">{t("brand.name")}</span>
          </Link>
          <div className="flex items-center gap-3">
            <button
              onClick={toggle}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all duration-200 ${ANIMATIONS.buttonPress} ${
                locale === "th" ? "bg-indigo-500/10 border-indigo-500/30 text-indigo-300" : "bg-slate-800/50 border-slate-700/50 text-slate-400 hover:text-white"
              }`}
            >
              <Globe size={14} />{t("lang.switch")}
            </button>
            <div className="hidden md:flex items-center gap-1.5 text-xs text-slate-400 border border-slate-800 bg-slate-900/30 px-3 py-1.5 rounded-full">
              <Shield size={12} className="text-emerald-400" />
              {t("nav.secureCheckout")}
            </div>
          </div>
        </div>
      </div>

      <div className="relative z-10 max-w-7xl mx-auto px-6 py-8">
        {/* Page Header */}
        <ScrollReveal>
        <div className="mb-8">
          <h1 className="text-3xl md:text-4xl font-display font-extrabold text-white">
            {selectedCategory !== "all" ? `${CATEGORY_META[selectedCategory].icon} ${t(`cat.${selectedCategory}`)}` : t("store.allProducts")}
          </h1>
          <p className="text-slate-400 mt-2 max-w-xl">
            {selectedCategory !== "all" ? t(`catDesc.${selectedCategory}`) : t("featured.subtitle")}
          </p>
        </div>
        </ScrollReveal>

        {/* Search & Filters */}
        <ScrollReveal delay={100}>
        <div className="flex flex-col md:flex-row gap-4 mb-8">
          <div className="relative flex-1">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500 w-4 h-4" />
            <input type="text" placeholder={t("store.search")} value={search} onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-slate-900/60 border border-slate-800 focus:border-indigo-500 text-slate-200 pl-10 pr-4 py-3 rounded-2xl text-sm outline-none transition-all duration-200 focus:ring-2 focus:ring-indigo-500/20" />
            {search && (
              <button onClick={() => setSearch("")} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white transition-colors duration-200">
                <X size={16} />
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Filter size={14} className="text-slate-500" />
            <select value={sortBy} onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
              className="bg-slate-900/60 border border-slate-800 focus:border-indigo-500 text-slate-300 px-4 py-3 rounded-2xl text-sm outline-none transition-all duration-200">
              <option value="popular">{t("store.sortPopular")}</option>
              <option value="newest">{t("store.sortNewest")}</option>
              <option value="price-low">{t("store.sortPriceLow")}</option>
              <option value="price-high">{t("store.sortPriceHigh")}</option>
              <option value="rating">{t("store.sortRating")}</option>
            </select>
          </div>
        </div>
        </ScrollReveal>

        {/* Category Tabs */}
        <ScrollReveal delay={150}>
        <div className="flex flex-wrap gap-2 mb-8">
          <button onClick={() => handleCategoryChange("all")}
            className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all duration-200 ${ANIMATIONS.buttonPress} ${
              selectedCategory === "all" ? "bg-indigo-500 text-white shadow-glow-sm" : "bg-slate-900/40 text-slate-400 border border-slate-800/60 hover:border-slate-700 hover:text-white"
            }`}>
            {t("store.allProducts")} ({PRODUCTS.length})
          </button>
          {ALL_CATEGORIES.map((cat) => {
            const count = PRODUCTS.filter((p) => p.category === cat).length;
            return (
              <button key={cat} onClick={() => handleCategoryChange(cat)}
                className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all duration-200 flex items-center gap-1.5 ${ANIMATIONS.buttonPress} ${
                  selectedCategory === cat ? "bg-indigo-500 text-white shadow-glow-sm" : "bg-slate-900/40 text-slate-400 border border-slate-800/60 hover:border-slate-700 hover:text-white"
                }`}>
                <span>{CATEGORY_META[cat].icon}</span>
                {t(`cat.${cat}`)}
                <span className="text-[10px] opacity-60">({count})</span>
              </button>
            );
          })}
        </div>
        </ScrollReveal>

        {/* Results count */}
        <div className="flex items-center justify-between mb-6">
          <p className="text-sm text-slate-500">
            {t("store.showing")} <span className="font-semibold text-slate-300">{filteredProducts.length}</span> {t("store.products")}
            {selectedCategory !== "all" && (
              <button onClick={() => handleCategoryChange("all")} className="ml-2 text-indigo-400 hover:text-indigo-300 text-xs transition-colors duration-200">
                {t("store.clearFilter")}
              </button>
            )}
          </p>
        </div>

        {/* Products Grid */}
        {isLoading ? (
          <SkeletonProductGrid count={8} />
        ) : filteredProducts.length === 0 ? (
          <div className="text-center py-20">
            <div className="w-16 h-16 bg-slate-800/50 rounded-2xl flex items-center justify-center mx-auto mb-4 text-slate-500">
              <Search size={28} />
            </div>
            <h3 className="text-lg font-bold text-slate-200">{t("store.noResults")}</h3>
            <p className="text-sm text-slate-500 mt-1 max-w-md mx-auto">{t("store.noResultsDesc")}</p>
            <button onClick={() => { setSearch(""); handleCategoryChange("all"); }}
              className={`mt-4 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm font-medium rounded-xl transition-all duration-200 ${ANIMATIONS.buttonPress}`}>
              {t("store.clearAll")}
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {filteredProducts.map((product, i) => (
              <Link key={product.id} to={`/store/${product.slug}`}
                className={`group bg-slate-900/40 border border-slate-800/60 rounded-3xl overflow-hidden flex flex-col animate-fade-in-up ${ANIMATIONS.cardHoverGlow}`}
                style={staggerDelay(i)}>
                <div className="relative h-44 overflow-hidden">
                  <img src={product.coverImageUrl} alt={product.name} loading="lazy"
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
                  <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/20 to-transparent" />
                  {product.badge && (
                    <span className="absolute top-3 left-3 px-2.5 py-1 bg-indigo-500/90 backdrop-blur-sm text-white text-[10px] font-bold uppercase tracking-wider rounded-full">
                      {product.badge}
                    </span>
                  )}
                  <div className="absolute top-3 right-3 flex items-center gap-1 px-2 py-0.5 bg-slate-950/70 backdrop-blur-sm rounded-full text-[10px] text-amber-400">
                    <Star size={10} className="fill-amber-400" /> {product.rating}
                  </div>
                </div>
                <div className="p-5 flex-1 flex flex-col">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800/80 text-slate-400 border border-slate-700/50">
                      {CATEGORY_META[product.category].icon} {t(`cat.${product.category}`)}
                    </span>
                  </div>
                  <h3 className="font-bold text-sm text-white group-hover:text-indigo-300 transition-colors duration-200 mb-1.5 line-clamp-2">
                    {product.name}
                  </h3>
                  <p className="text-xs text-slate-500 line-clamp-2 mb-4 flex-1">{product.shortDescription}</p>
                  <div className="flex items-end justify-between pt-3 border-t border-slate-800/60">
                    <div>
                      <span className="text-xl font-extrabold text-white">{formatPrice(product.priceAmount)}</span>
                      <span className="text-[10px] text-slate-500 ml-1.5">{formatSalesCount(product.salesCount)} {t("featured.sold")}</span>
                    </div>
                    <div className="w-8 h-8 rounded-xl bg-indigo-500/10 flex items-center justify-center text-indigo-400 group-hover:bg-indigo-500 group-hover:text-white transition-all duration-300 group-hover:scale-110">
                      <ArrowRight size={14} />
                    </div>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}

        {/* Trust Bar */}
        <ScrollReveal delay={100}>
        <div className="mt-16 flex flex-wrap items-center justify-center gap-8 text-xs text-slate-500 border-t border-slate-800/50 pt-8">
          <div className="flex items-center gap-2"><Shield size={14} className="text-emerald-500/60" />{t("store.trust1")}</div>
          <div className="flex items-center gap-2"><Sparkles size={14} className="text-indigo-400/60" />{t("store.trust2")}</div>
          <div className="flex items-center gap-2"><TrendingUp size={14} className="text-amber-400/60" />{t("store.trust3")}</div>
        </div>
        </ScrollReveal>
      </div>
    </div>
  );
}

import { ArrowRight, Check, Tag } from "lucide-react";
import { useLang } from "../../i18n/LanguageContext";
import { ANIMATIONS } from "../../lib/animations";
import { formatPrice } from "../../data/products";

interface BundleCardProps {
  name: string;
  description?: string;
  productNames: string[];
  originalPrice: number;
  discountType: "percentage" | "fixed";
  discountValue: number;
  badge?: string;
  onBuy?: () => void;
}

/**
 * Bundle Card — displays a product bundle with discount, original price, and CTA.
 */
export default function BundleCard({
  name,
  description,
  productNames,
  originalPrice,
  discountType,
  discountValue,
  badge,
  onBuy,
}: BundleCardProps) {
  const { locale } = useLang();

  const discountAmount =
    discountType === "percentage"
      ? Math.round(originalPrice * (discountValue / 100))
      : discountValue;

  const finalPrice = Math.max(originalPrice - discountAmount, 0);
  const savingsPercent = Math.round((discountAmount / originalPrice) * 100);

  return (
    <div
      className={`relative bg-slate-900/40 border border-slate-800/60 rounded-3xl p-6 hover:border-indigo-500/30 transition-all duration-300 group ${ANIMATIONS.cardHoverGlow}`}
    >
      {/* Badge */}
      {badge && (
        <div className="absolute -top-3 left-6">
          <span className="inline-flex items-center gap-1 px-3 py-1 bg-gradient-to-r from-amber-500 to-orange-500 text-white text-[10px] font-bold uppercase tracking-wider rounded-full shadow-lg">
            <Tag size={10} />
            {badge}
          </span>
        </div>
      )}

      {/* Savings badge */}
      <div className="absolute top-4 right-4">
        <span className="inline-flex items-center px-2.5 py-1 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[10px] font-bold rounded-full">
          {locale === "th" ? "ประหยัด" : "Save"} {savingsPercent}%
        </span>
      </div>

      {/* Content */}
      <div className="space-y-4 mt-2">
        <h3 className="text-lg font-bold text-white group-hover:text-indigo-300 transition-colors">
          {name}
        </h3>

        {description && (
          <p className="text-sm text-slate-400 leading-relaxed">{description}</p>
        )}

        {/* Product list */}
        <div className="space-y-2">
          <p className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">
            {locale === "th" ? "รวมสินค้า:" : "Includes:"}
          </p>
          {productNames.map((name, i) => (
            <div key={i} className="flex items-center gap-2 text-sm text-slate-300">
              <Check size={14} className="text-emerald-400 shrink-0" />
              <span>{name}</span>
            </div>
          ))}
        </div>

        {/* Pricing */}
        <div className="pt-4 border-t border-slate-800/60 space-y-2">
          <div className="flex items-center gap-3">
            <span className="text-3xl font-extrabold text-white">
              {formatPrice(finalPrice)}
            </span>
            <span className="text-lg text-slate-500 line-through">
              {formatPrice(originalPrice)}
            </span>
          </div>
          <p className="text-[10px] text-slate-500">
            {locale === "th"
              ? "จ่ายครั้งเดียว · อัปเดตตลอดชีพ"
              : "One-time payment · Lifetime updates"}
          </p>
        </div>

        {/* CTA */}
        <button
          onClick={() => onBuy?.()}
          className={`w-full py-3.5 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white font-bold rounded-xl shadow-glow-md transition-all duration-200 flex items-center justify-center gap-2 group/btn text-sm ${ANIMATIONS.buttonPress}`}
        >
          {locale === "th" ? "ซื้อแพ็กเกจนี้" : "Get This Bundle"}
          <ArrowRight
            size={16}
            className="group-hover/btn:translate-x-0.5 transition-transform"
          />
        </button>
      </div>
    </div>
  );
}

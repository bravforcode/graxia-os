import { useState, useEffect } from "react";
import { ShoppingCart, X } from "lucide-react";
import { useLang } from "../../i18n/LanguageContext";

/**
 * Social Proof Popup — shows rotating "someone just purchased" notifications.
 * Uses fake data for demo; replace with real API when backend is ready.
 */

const RECENT_PURCHASES_TH = [
  { name: "สมชาย", location: "กรุงเทพฯ", product: "ChatGPT Power Prompts Bundle" },
  { name: "นภัส", location: "เชียงใหม่", product: "Notion Life OS" },
  { name: "วิชัย", location: "ภูเก็ต", product: "SaaS Boilerplate Starter" },
  { name: "สุภาพร", location: "ขอนแก่น", product: "Email Marketing Swipe File" },
  { name: "ธนวัฒน์", location: "พัทยา", product: "Dark Mode UI Kit Pro" },
  { name: "ปิยะนุช", location: "หาดใหญ่", product: "Freelancer Command Center" },
  { name: "จิรัฐติกาล", location: "ระยอง", product: "YouTube Growth Toolkit" },
  { name: "มณี", location: "นครราชสีมา", product: "SEO Mastery Guide" },
  { name: "อรุณ", location: "สุราษฎร์ธานี", product: "12-Week Fitness Program" },
  { name: "พิมพ์ใจ", location: "อุดรธานี", product: "Copywriting Masterclass" },
];

const RECENT_PURCHASES_EN = [
  { name: "Sarah", location: "Bangkok", product: "ChatGPT Power Prompts Bundle" },
  { name: "Marcus", location: "Chiang Mai", product: "Notion Life OS" },
  { name: "David", location: "Phuket", product: "SaaS Boilerplate Starter" },
  { name: "Lisa", location: "Khon Kaen", product: "Email Marketing Swipe File" },
  { name: "Tyler", location: "Pattaya", product: "Dark Mode UI Kit Pro" },
  { name: "Emma", location: "Hat Yai", product: "Freelancer Command Center" },
  { name: "Alex", location: "Rayong", product: "YouTube Growth Toolkit" },
  { name: "Rachel", location: "Korat", product: "SEO Mastery Guide" },
  { name: "Kevin", location: "Surat Thani", product: "12-Week Fitness Program" },
  { name: "Priya", location: "Udon Thani", product: "Copywriting Masterclass" },
];

function timeAgo(minutes: number, locale: string): string {
  if (locale === "th") {
    if (minutes < 2) return "เมื่อสักครู่";
    if (minutes < 60) return `${minutes} นาทีที่แล้ว`;
    return `${Math.floor(minutes / 60)} ชม. ที่แล้ว`;
  }
  if (minutes < 2) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  return `${Math.floor(minutes / 60)}h ago`;
}

export default function SocialProofPopup() {
  const { locale } = useLang();
  const [visible, setVisible] = useState(false);
  const [current, setCurrent] = useState(0);
  const [dismissed, setDismissed] = useState(false);
  const [minutesAgo] = useState(() => Math.floor(Math.random() * 30) + 1);

  const purchases =
    locale === "th" ? RECENT_PURCHASES_TH : RECENT_PURCHASES_EN;

  useEffect(() => {
    if (dismissed) return;

    // Show first popup after 30s, then every 45s
    const showTimer = setTimeout(() => {
      setVisible(true);
    }, 30000);

    const interval = setInterval(() => {
      setVisible(true);
      setCurrent((prev) => (prev + 1) % purchases.length);
    }, 45000);

    return () => {
      clearTimeout(showTimer);
      clearInterval(interval);
    };
  }, [dismissed, purchases.length]);

  // Auto-hide after 6 seconds
  useEffect(() => {
    if (!visible) return;
    const timer = setTimeout(() => setVisible(false), 6000);
    return () => clearTimeout(timer);
  }, [visible, current]);

  if (dismissed || !visible) return null;

  const p = purchases[current];

  return (
    <div className="fixed bottom-6 left-6 z-[90] animate-fade-in-up">
      <div className="flex items-center gap-3 bg-slate-900/90 backdrop-blur-xl border border-slate-700/60 rounded-2xl px-4 py-3 shadow-2xl max-w-sm">
        {/* Avatar */}
        <div className="w-10 h-10 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white text-xs font-bold shrink-0">
          {p.name[0]}
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <p className="text-xs text-slate-300 leading-snug">
            <span className="font-semibold text-white">{p.name}</span>{" "}
            <span className="text-slate-500">from</span>{" "}
            <span className="font-medium text-slate-300">{p.location}</span>
          </p>
          <p className="text-[10px] text-slate-500 truncate mt-0.5">
            {locale === "th" ? "เพิ่งซื้อ" : "just purchased"}{" "}
            <span className="text-indigo-400 font-medium">{p.product}</span>
          </p>
        </div>

        {/* Icon + Time */}
        <div className="flex flex-col items-center gap-1 shrink-0">
          <ShoppingCart size={14} className="text-emerald-400" />
          <span className="text-[9px] text-slate-600">
            {timeAgo(minutesAgo, locale)}
          </span>
        </div>

        {/* Close */}
        <button
          onClick={() => {
            setVisible(false);
            setDismissed(true);
          }}
          className="absolute top-2 right-2 p-0.5 text-slate-600 hover:text-slate-400 transition-colors"
        >
          <X size={12} />
        </button>
      </div>
    </div>
  );
}

import { useState, useEffect, useCallback } from "react";
import { X, Gift, Mail, Sparkles } from "lucide-react";
import { useLang } from "../../i18n/LanguageContext";
import { ANIMATIONS } from "../../lib/animations";

/**
 * Exit-Intent Popup — shows when user's mouse leaves the viewport (top edge).
 * Captures email and offers a discount code.
 * Only shows once per session (localStorage flag).
 */
export default function ExitIntentPopup() {
  const { locale } = useLang();
  const [show, setShow] = useState(false);
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [discountCode] = useState("WELCOMEBACK15");

  useEffect(() => {
    // Check if already shown this session
    try {
      if (sessionStorage.getItem("ai-factory-exit-popup")) return;
    } catch {}

    const handleMouseLeave = (e: MouseEvent) => {
      // Only trigger when mouse leaves from the top edge
      if (e.clientY <= 0 && !submitted) {
        setShow(true);
        try {
          sessionStorage.setItem("ai-factory-exit-popup", "1");
        } catch {}
        document.removeEventListener("mouseleave", handleMouseLeave);
      }
    };

    document.addEventListener("mouseleave", handleMouseLeave);
    return () => document.removeEventListener("mouseleave", handleMouseLeave);
  }, [submitted]);

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      if (!email.trim()) return;
      setSubmitted(true);

      // Log the lead capture event
      fetch("/api/v1/funnel/events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          organization_id: "00000000-0000-0000-0000-000000000001",
          event_type: "lead_capture",
          metadata_json: { source: "exit_intent_popup", email },
        }),
      }).catch(() => {});
    },
    [email]
  );

  if (!show) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm animate-fade-in">
      <div
        className={`relative w-full max-w-md mx-4 bg-slate-900 border border-slate-700/60 rounded-3xl shadow-2xl overflow-hidden animate-fade-in-up`}
      >
        {/* Close button */}
        <button
          onClick={() => setShow(false)}
          className="absolute top-4 right-4 z-10 p-1.5 rounded-full bg-slate-800/80 text-slate-400 hover:text-white hover:bg-slate-700 transition-all duration-200"
        >
          <X size={16} />
        </button>

        {/* Gradient accent */}
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-indigo-500 via-purple-500 to-cyan-500" />

        <div className="p-8">
          {submitted ? (
            /* Success State */
            <div className="text-center space-y-4">
              <div className="w-16 h-16 bg-emerald-500/10 border border-emerald-500/20 rounded-2xl flex items-center justify-center mx-auto">
                <Sparkles size={28} className="text-emerald-400" />
              </div>
              <h3 className="text-xl font-bold text-white">
                {locale === "th" ? "ขอบคุณ!" : "You're in!"}
              </h3>
              <p className="text-sm text-slate-400">
                {locale === "th"
                  ? `ใช้โค้ดนี้เพื่อรับส่วนลด 15%:`
                  : `Use this code for 15% off your first purchase:`}
              </p>
              <div className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-500/10 border border-indigo-500/30 rounded-xl">
                <span className="font-mono font-bold text-lg text-indigo-300">
                  {discountCode}
                </span>
              </div>
              <button
                onClick={() => setShow(false)}
                className={`block mx-auto px-6 py-2.5 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white text-sm font-semibold rounded-xl transition-all duration-200 ${ANIMATIONS.buttonPress}`}
              >
                {locale === "th" ? "ช็อปเลย" : "Shop Now"}
              </button>
            </div>
          ) : (
            /* Capture State */
            <div className="text-center space-y-4">
              <div className="w-16 h-16 bg-amber-500/10 border border-amber-500/20 rounded-2xl flex items-center justify-center mx-auto">
                <Gift size={28} className="text-amber-400" />
              </div>
              <h3 className="text-xl font-bold text-white">
                {locale === "th"
                  ? "ก่อนไป — รับส่วนลด 15%!"
                  : "Wait — get 15% off!"}
              </h3>
              <p className="text-sm text-slate-400 leading-relaxed">
                {locale === "th"
                  ? "กรอกอีเมลของคุณเพื่อรับโค้ดส่วนลดสำหรับสินค้าทุกชิ้น"
                  : "Enter your email to get a discount code for any product"}
              </p>
              <form onSubmit={handleSubmit} className="space-y-3">
                <div className="relative">
                  <Mail
                    size={16}
                    className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500"
                  />
                  <input
                    type="email"
                    required
                    placeholder={
                      locale === "th" ? "อีเมลของคุณ" : "Your email address"
                    }
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full bg-slate-800/60 border border-slate-700 focus:border-indigo-500 text-slate-200 pl-10 pr-4 py-3 rounded-xl text-sm outline-none transition-all duration-200 focus:ring-2 focus:ring-indigo-500/20"
                    autoFocus
                  />
                </div>
                <button
                  type="submit"
                  className={`w-full py-3 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white text-sm font-bold rounded-xl transition-all duration-200 ${ANIMATIONS.buttonPress}`}
                >
                  {locale === "th"
                    ? "รับส่วนลด 15% ของฉัน"
                    : "Get My 15% Discount"}
                </button>
              </form>
              <p className="text-[10px] text-slate-600">
                {locale === "th"
                  ? "ไม่สแปม อีเมลใช้สำหรับส่งโค้ดเท่านั้น"
                  : "No spam. Email used only for the discount code."}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

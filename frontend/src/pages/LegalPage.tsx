import { Link } from "react-router-dom";
import { useLang } from "@/i18n/LanguageContext";

export default function LegalPage({ type }: { type: "privacy" | "terms" }) {
  const { t, locale } = useLang();

  const th = locale === "th";
  const title = type === "privacy"
    ? (th ? "นโยบายความเป็นส่วนตัว" : "Privacy Policy")
    : (th ? "ข้อกำหนดการใช้งาน" : "Terms of Service");

  const sections = type === "privacy"
    ? [
        { h: th ? "ข้อมูลที่เราเก็บ" : "Data we collect",
          b: th
            ? "เราเก็บอีเมลสำหรับการสั่งซื้อและส่งสินค้าดิจิทัล, ข้อมูลการชำระเงินผ่าน Stripe (เราไม่เก็บเลขบัตร), และข้อมูลการใช้งานพื้นฐาน (views/clicks) เพื่อปรับปรุงสินค้า"
            : "We collect your email for orders and digital delivery, payment data via Stripe (we never store card numbers), and basic usage data (views/clicks) to improve our products." },
        { h: th ? "การยินยอมและสิทธิ์ของคุณ (พ.ร.บ. คุ้มครองข้อมูลส่วนบุคคล)" : "Consent & your rights (PDPA)",
          b: th
            ? "การส่งอีเมลของคุณถือเป็นการยินยอมให้เราประมวลผลข้อมูลตามนโยบายนี้ คุณสามารถขอเข้าถึง แก้ไข หรือลบข้อมูลได้ทุกเมื่อโดยติดต่อ support@aifactory.store"
            : "Submitting your email constitutes consent to process data per this policy. You may request access, correction, or deletion anytime via support@aifactory.store." },
        { h: th ? "การแชร์ข้อมูล" : "Data sharing",
          b: th
            ? "เราแชร์ข้อมูลกับ Stripe (การชำระเงิน), Resend (การส่งอีเมล) เท่านั้น และไม่ขายข้อมูลของคุณ"
            : "We share data only with Stripe (payments) and Resend (email delivery). We never sell your data." },
        { h: th ? "คุกกี้" : "Cookies",
          b: th
            ? "เราใช้ localStorage เพื่อจำภาษาที่คุณเลือกและคุกกี้ของ Stripe เพื่อการชำระเงินที่ปลอดภัย"
            : "We use localStorage to remember your language and Stripe cookies for secure checkout." },
      ]
    : [
        { h: th ? "สินค้าดิจิทัล" : "Digital products",
          b: th
            ? "สินค้าเป็นไฟล์ดิจิทัลที่ส่งทันทีหลังชำระเงินผ่านอีเมล ไม่สามารถคืนเงินได้หลังได้รับลิงก์ดาวน์โหลด ยกเว้นตามระยะเวลารับประกันที่ระบุบนสินค้า"
            : "Products are digital files delivered by email immediately after payment. No refunds after the download link is issued, except within the guarantee period stated on the product." },
        { h: th ? "สิทธิ์การใช้งาน" : "License",
          b: th
            ? "ซื้อแล้วใช้ส่วนตัวหรือเชิงพาณิชย์ได้ ห้ามนำไปขายต่อหรือแจกจ่ายซ้ำโดยไม่ได้รับอนุญาต"
            : "Purchases may be used personally or commercially. Reselling or redistributing without permission is prohibited." },
        { h: th ? "ความรับผิด" : "Liability",
          b: th
            ? "สินค้าให้ตามสภาพ ผลลัพธ์ที่ได้จากการใช้เครื่องมือ AI ขึ้นอยู่กับการใช้งานของแต่ละบุคคล"
            : "Products are provided as-is. Results from using AI tools depend on individual usage." },
      ];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans overflow-x-clip">
      <div className="sticky top-4 z-50 flex justify-center px-4">
        <div className="pill-nav w-full max-w-5xl flex h-[56px] items-center justify-between px-5">
          <Link to="/" className="flex items-center gap-2 group">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-cyan-400 flex items-center justify-center font-mono font-bold text-sm text-slate-950">AI</div>
            <span className="font-serif font-bold text-lg text-slate-100">{t("brand.name")}</span>
          </Link>
          <Link to="/store" className="text-sm text-slate-400 hover:text-slate-100 transition-colors">
            {t("nav.products")}
          </Link>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-6 py-16">
        <h1 className="font-serif font-medium text-3xl md:text-4xl tracking-tighter text-balance text-slate-100 mb-8">{title}</h1>
        <div className="space-y-6">
          {sections.map((s) => (
            <div key={s.h} className="edge-light bg-slate-900/40 border border-slate-800 rounded-2xl p-6">
              <h2 className="font-semibold text-slate-200 mb-2">{s.h}</h2>
              <p className="text-sm text-slate-400 leading-relaxed">{s.b}</p>
            </div>
          ))}
        </div>
        <p className="text-xs text-slate-500 mt-10">{th ? "อัปเดตล่าสุด: สิงหาคม 2026" : "Last updated: August 2026"}</p>
      </div>
    </div>
  );
}

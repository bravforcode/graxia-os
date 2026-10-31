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
            ? "เราเก็บอีเมลสำหรับคำขอซื้อหรือส่งมอบดิจิทัล และข้อมูล event แบบลดข้อมูลเพื่อวัด attribution โดยไม่ใส่ PII ใน metadata analytics"
            : "We collect email for purchase or digital-delivery requests and minimized event data for attribution. Analytics metadata must not contain PII." },
        { h: th ? "การยินยอมและสิทธิ์ของคุณ (พ.ร.บ. คุ้มครองข้อมูลส่วนบุคคล)" : "Consent & your rights (PDPA)",
          b: th
            ? "การส่งอีเมลไม่ถือเป็นการยินยอม marketing โดยอัตโนมัติ ระบบจะส่ง nurture เมื่อคุณเลือกยินยอมพร้อม consent version เท่านั้น คุณสามารถขอเข้าถึง แก้ไข หรือลบข้อมูลได้ที่ support@graxia.store"
            : "Submitting an email does not automatically grant marketing consent. Nurture requires explicit consent and a consent version. You may request access, correction, or deletion at support@graxia.store." },
        { h: th ? "การแชร์ข้อมูล" : "Data sharing",
          b: th
            ? "เราแชร์ข้อมูลกับ provider ที่เปิดใช้งานตามวัตถุประสงค์ที่จำเป็นเท่านั้น และไม่ขายข้อมูลของคุณ"
            : "We share data only with configured providers for necessary purposes. We do not sell your data." },
        { h: th ? "คุกกี้" : "Cookies",
          b: th
            ? "เราใช้ localStorage เพื่อจำภาษาที่คุณเลือกและคุกกี้ของ Stripe เพื่อการชำระเงินที่ปลอดภัย"
            : "We use localStorage to remember your language and Stripe cookies for secure checkout." },
      ]
    : [
        { h: th ? "สินค้าดิจิทัล" : "Digital products",
          b: th
            ? "สินค้าเป็นไฟล์ดิจิทัลที่ส่งตาม delivery asset หลัง event การซื้อได้รับการยืนยัน เงื่อนไขคืนเงินและการเข้าถึงให้ยึดตามที่ระบุบนหน้าสินค้า"
            : "Products are delivered according to the configured delivery asset after a purchase event is verified. Refund and access terms are those stated on the product page." },
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
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-cyan-400 flex items-center justify-center font-mono font-bold text-sm text-slate-950">GX</div>
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
        <p className="text-xs text-slate-500 mt-10">{th ? "อัปเดตล่าสุด: กันยายน 2026" : "Last updated: September 2026"}</p>
      </div>
    </div>
  );
}

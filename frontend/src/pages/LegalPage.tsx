import { Link } from "react-router-dom";
import { useLang } from "@/i18n/LanguageContext";

type LegalPageType = "privacy" | "terms" | "refund" | "delivery";

export default function LegalPage({ type }: { type: LegalPageType }) {
  const { t, locale } = useLang();

  const th = locale === "th";
  const title = {
    privacy: th ? "นโยบายความเป็นส่วนตัว" : "Privacy Policy",
    terms: th ? "ข้อกำหนดการใช้งาน" : "Terms of Service",
    refund: th ? "นโยบายการคืนเงิน" : "Refund Policy",
    delivery: th ? "นโยบายการส่งมอบ" : "Delivery Information",
  }[type];

  const sections = type === "privacy"
    ? [
        { h: th ? "ข้อมูลที่เราเก็บ" : "Data we collect",
          b: th
            ? "เราเก็บอีเมลสำหรับคำขอซื้อหรือส่งมอบดิจิทัล และข้อมูล event แบบลดข้อมูลเพื่อวัด attribution โดยไม่ใส่ PII ใน metadata analytics"
            : "We collect email for purchase or digital-delivery requests and minimized event data for attribution. Analytics metadata must not contain PII." },
        { h: th ? "การยินยอมและสิทธิ์ของคุณ (พ.ร.บ. คุ้มครองข้อมูลส่วนบุคคล)" : "Consent & your rights (PDPA)",
          b: th
            ? "การส่งอีเมลไม่ถือเป็นการยินยอม marketing โดยอัตโนมัติ ระบบจะส่ง nurture เมื่อคุณเลือกยินยอมพร้อม consent version เท่านั้น คุณสามารถขอเข้าถึง แก้ไข หรือลบข้อมูลได้ผ่านช่องทางติดต่อที่ระบุในหน้าเว็บไซต์"
            : "Submitting an email does not automatically grant marketing consent. Nurture requires explicit consent and a consent version. You may request access, correction, or deletion through the contact channel listed on the website." },
        { h: th ? "การแชร์ข้อมูล" : "Data sharing",
          b: th
            ? "เราแชร์ข้อมูลกับ provider ที่เปิดใช้งานตามวัตถุประสงค์ที่จำเป็นเท่านั้น และไม่ขายข้อมูลของคุณ"
            : "We share data only with configured providers for necessary purposes. We do not sell your data." },
        { h: th ? "คุกกี้" : "Cookies",
          b: th
            ? "เราใช้ localStorage เพื่อจำภาษาที่คุณเลือกและคุกกี้ของ Stripe เพื่อการชำระเงินที่ปลอดภัย"
            : "We use localStorage to remember your language and Stripe cookies for secure checkout." },
      ]
    : type === "terms"
    ? [
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
      ]
    : type === "refund"
    ? [
        { h: th ? "สินค้าดิจิทัลและการขอคืนเงิน" : "Digital products and refund requests",
          b: th
            ? "สินค้าดิจิทัลเริ่มส่งมอบหลัง provider ยืนยันสถานะการชำระเงิน หากไฟล์เปิดไม่ได้ ไฟล์ไม่ตรงรายการ หรือเกิดการส่งมอบซ้ำ กรุณาติดต่อภายใน 7 วันพร้อมเลขอ้างอิงคำสั่งซื้อเพื่อให้ตรวจสอบเป็นรายกรณี"
            : "Digital delivery begins after the provider verifies payment. If a file cannot be opened, does not match the listing, or delivery is duplicated, contact us within 7 days with the order reference for case-by-case review." },
        { h: th ? "กรณีที่อาจไม่เข้าเงื่อนไข" : "Cases that may not qualify",
          b: th
            ? "คำขอที่อยู่นอกช่วงเวลา ไฟล์ถูกใช้งานหรือแจกจ่ายแล้ว หรือไม่สามารถยืนยันคำสั่งซื้อ อาจไม่เข้าเงื่อนไขคืนเงิน ทั้งนี้การตัดสินใจจะอิงหลักฐานคำสั่งซื้อและสถานะ provider"
            : "Requests outside the stated window, redistributed files, or requests without a verifiable order may not qualify. Decisions rely on order evidence and provider status." },
        { h: th ? "ช่องทางติดต่อ" : "How to contact us",
          b: th
            ? "ส่งรายละเอียดผ่านช่องทาง support ที่แสดงในเว็บไซต์ อย่าส่ง secret key หรือข้อมูลบัตร โดยระบบจะใช้เฉพาะข้อมูลที่จำเป็นต่อการตรวจสอบ"
            : "Use the support channel shown on the website. Do not send secret keys or card data; only information needed to verify the request is used." },
      ]
    : [
        { h: th ? "ไฟล์ฟรีและไฟล์ที่ซื้อ" : "Free and purchased files",
          b: th
            ? "ไฟล์ฟรีส่งผ่าน delivery token ที่มีอายุจำกัด ส่วนสินค้าที่ซื้อจะเปิดให้เมื่อ payment webhook หรือหลักฐาน provider ผ่านการตรวจสอบแล้ว"
            : "Free files are delivered through a time-limited delivery token. Purchased files open only after a payment webhook or provider evidence is verified." },
        { h: th ? "การเข้าถึงและการหมดอายุ" : "Access and expiry",
          b: th
            ? "ลิงก์ delivery อาจมีวันหมดอายุหรือจำนวนครั้งดาวน์โหลดตาม asset ที่ตั้งค่าไว้ หากลิงก์ใช้ไม่ได้ ให้ติดต่อพร้อม delivery token หรือ order reference"
            : "Delivery links may have an expiry or download limit configured for the asset. If a link fails, contact us with the delivery token or order reference." },
        { h: th ? "สถานะที่หน้าเว็บแสดง" : "Status shown on the site",
          b: th
            ? "หน้า return จาก checkout ไม่ถือเป็นหลักฐานการชำระเงิน ระบบจะแสดงการส่งมอบเมื่อ backend ได้รับและตรวจสอบ event จาก provider แล้วเท่านั้น"
            : "A checkout return page is not payment evidence. Delivery is shown only after the backend receives and verifies a provider event." },
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
        <nav aria-label="Legal pages" className="mt-4 flex flex-wrap gap-4 text-xs text-indigo-300">
          <Link to="/privacy">{th ? "ความเป็นส่วนตัว" : "Privacy"}</Link>
          <Link to="/terms">{th ? "ข้อกำหนด" : "Terms"}</Link>
          <Link to="/refund">{th ? "คืนเงิน" : "Refunds"}</Link>
          <Link to="/delivery">{th ? "การส่งมอบ" : "Delivery"}</Link>
        </nav>
      </div>
    </div>
  );
}

import { useState } from "react"

const REVENUE_OS_API = "https://graxia-revenue-os.onrender.com"
const PRODUCTS = [
  {
    id: "dda2e1b0-cd14-4d52-8950-0d7bad791ffb",
    slug: "revenue-os-starter",
    name: "Starter",
    price: 499,
    priceLabel: "฿499",
    period: "/เดือน",
    badge: null,
    accent: "paper",
    promise: "สำหรับร้านเริ่มขาย — ปิดการขายครบวงจรช่องทางเดียว",
    features: ["1 ช่องทางขาย (Shopee / Shopify / TikTok)", "ออเดอร์ → ส่งของ → ใบเสร็จ อัตโนมัติ", "อีเมลติดตามลูกค้าพื้นฐาน", "CEO Dashboard ดูยอด Realtime", "ผู้ใช้ 1 คน"],
    cta: "เริ่ม Starter",
    subtext: "ยกเลิกได้ทุกเดือน",
  },
  {
    id: "9c0c0481-aee7-4c45-8ef8-596a737d6326",
    slug: "revenue-os-growth",
    name: "Growth",
    price: 1490,
    priceLabel: "฿1,490",
    period: "/เดือน",
    badge: "นิยมสุด",
    accent: "brass",
    promise: "สำหรับร้าน 1–5 ล้าน/ปี — ทุกช่องทาง + AI คุมงบแทนคุณ",
    features: ["ทุกช่องทาง + สต็อกกลาง", "แคมเปญ + ขออนุมัติก่อนยิงแอด (CEO)", "AI เปลี่ยนงบ/ปิดแคมเปญแทนคน", "ผู้ใช้ 5 คน + สิทธิ์ Approvals", "Affiliate + Email อัตโนมัติ"],
    cta: "เริ่ม Growth",
    subtext: "ประหยัด 3 เท่า vs จ้างแอดมิน",
  },
  {
    id: "aff2aa7a-e681-4f4a-9d98-18759dcd06cb",
    slug: "revenue-os-scale",
    name: "Scale",
    price: 4900,
    priceLabel: "฿4,900",
    period: "/เดือน",
    badge: "คุ้มสุด",
    accent: "ink",
    promise: "สำหรับ 5–20 ล้าน/ปี — SLA 99.5% + ทีมตั้งค่าให้",
    features: ["ทุกอย่างใน Growth + SLA 99.5%", "Onboarding 1 เดือน + ตั้งค่าให้ครบ", "Incident เฝ้าระวัง 24 ชม.", "Support พรีเมียม + Line ส่วนตัว", "Custom funnel ตามธุรกิจคุณ"],
    cta: "เริ่ม Scale",
    subtext: "ROI > ค่าเช่า 1 วัน",
  },
] as const

export default function RevenueOSFunnel() {
  const [loadingId, setLoadingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [emailOpen, setEmailOpen] = useState<string | null>(null)
  const [email, setEmail] = useState("")

  async function checkout(productId: string) {
    const customerEmail = email || `guest_${Date.now()}@graxia.app`
    if (!email) {
      setEmailOpen(productId)
      return
    }
    setLoadingId(productId)
    setError(null)
    try {
      const res = await fetch(`${REVENUE_OS_API}/api/checkout/session`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          product_id: productId,
          mode: "subscription",
          success_url: `${window.location.origin}/checkout/success?session_id={CHECKOUT_SESSION_ID}`,
          cancel_url: `${window.location.origin}/revenue-os?canceled=1`,
          customer_email: customerEmail,
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || "สร้างลิงก์จ่ายเงินไม่สำเร็จ")
      if (data.checkout_url) window.location.href = data.checkout_url
      else throw new Error("ไม่ได้รับลิงก์ Stripe")
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "เกิดข้อผิดพลาด")
    } finally {
      setLoadingId(null)
    }
  }

  function handleEmailSubmit(productId: string) {
    if (!email || !email.includes("@")) {
      setError("กรุณากรอกอีเมลให้ถูกต้อง")
      return
    }
    setEmailOpen(null)
    checkout(productId)
  }

  return (
    <div className="min-h-screen bg-[#F8F6F3] text-[#0F172A] selection:bg-[#B45309]/20 selection:text-[#0F172A]">
      <style>{`@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=JetBrains+Mono:wght@400;600&family=Sarabun:wght@400;600;700&display=swap');`}</style>

      {/* Blueprint grid */}
      <div className="pointer-events-none fixed inset-0">
        <div className="absolute inset-0 opacity-[0.04]" style={{ backgroundImage: `linear-gradient(to right, #0F172A 1px, transparent 1px), linear-gradient(to bottom, #0F172A 1px, transparent 1px)`, backgroundSize: "32px 32px" }} />
        <div className="absolute inset-x-0 top-0 h-[1px] bg-[#0F172A]/10" />
        <div className="absolute left-6 md:left-10 top-0 bottom-0 w-px bg-[#0F172A]/10 hidden md:block" />
        <div className="absolute right-6 md:right-10 top-0 bottom-0 w-px bg-[#0F172A]/10 hidden md:block" />
      </div>

      {/* Header — blueprint rail */}
      <header className="sticky top-0 z-40 backdrop-blur-xl bg-[#F8F6F3]/80 border-b border-[#0F172A]/10">
        <div className="mx-auto max-w-[1200px] px-6 md:px-10 h-[56px] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-[8px] bg-[#0F172A] text-[#F8F6F3] grid place-items-center font-mono text-[10px] tracking-[0.2em] font-semibold">GX</div>
            <span className="font-mono text-[11px] tracking-[0.18em] text-[#0F172A]">GRAXIA / REVENUE OS</span>
            <span className="hidden md:inline-flex items-center gap-1.5 ml-3 pl-3 border-l border-[#0F172A]/10 font-mono text-[10px] tracking-[0.12em] text-[#64748B]">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" /> LIVE
            </span>
          </div>
          <div className="hidden md:flex items-center gap-6 font-mono text-[11px] tracking-[0.12em] text-[#475569]">
            <a href="#spec" className="hover:text-[#0F172A]">SPEC</a>
            <a href="#pricing" className="hover:text-[#0F172A]">PRICING</a>
            <a href="#faq" className="hover:text-[#0F172A]">FAQ</a>
          </div>
          <a href="#pricing" className="hidden md:inline-flex h-8 px-4 items-center bg-[#0F172A] text-white text-[11px] tracking-[0.12em] font-mono hover:bg-[#1E293B] transition-colors">
            ดูราคา →
          </a>
        </div>
      </header>

      {/* Hero — editorial, not centered card */}
      <section className="relative mx-auto max-w-[1200px] px-6 md:px-10 pt-10 md:pt-16 pb-10">
        <div className="grid md:grid-cols-[1.15fr_0.85fr] gap-10 md:gap-8 items-start">
          <div>
            <div className="inline-flex items-center gap-2 border border-[#B45309]/20 bg-[#B45309]/5 px-2.5 py-1 text-[10px] font-mono tracking-[0.14em] text-[#92400E]">
              <span className="w-1 h-1 bg-[#B45309] rounded-full" /> DECLASSIFIED — OPERATIONS MANUAL 01
            </div>
            <h1 className="mt-5 font-[DM_Serif_Display] text-[40px] md:text-[64px] leading-[0.9] tracking-[-0.03em] text-[#0F172A]">
              ระบบปิดการขาย
              <br />
              <span className="text-[#B45309]">อัตโนมัติ 100%</span>
              <br />
              <span className="font-mono text-[14px] md:text-[15px] tracking-[0.12em] font-normal text-[#475569]">ตั้งแต่ยิงแอด → รับเงิน → ส่งของ → ตามลูกค้า</span>
            </h1>
            <p className="mt-5 max-w-[52ch] text-[15px] leading-7 text-[#334155] font-[Sarabun]">
              สำหรับร้านไทยที่ขายจริง ไม่ใช่ร้านทดลอง — Revenue OS คุม funnel แทนคน, ขออนุมัติก่อนยิงงบ, และส่งของทันทีหลัง Stripe ยืนยัน.
              <span className="text-[#0F172A] font-semibold"> ไม่ต้องจ้างแอดมินเพิ่ม.</span>
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <a href="#pricing" className="inline-flex h-11 px-6 items-center gap-2 bg-[#B45309] text-white text-sm font-semibold hover:bg-[#92400E] transition-colors">
                ดู 3 แผน → <span className="opacity-70 font-mono text-xs">499 / 1490 / 4900</span>
              </a>
              <div className="inline-flex items-center gap-2 text-xs font-mono tracking-[0.08em] text-[#64748B] border border-[#0F172A]/10 px-3">
                <span className="w-2 h-2 rounded-full border border-[#0F172A]/20 grid place-items-center"><span className="w-1 h-1 bg-emerald-500 rounded-full" /></span>
                Stripe Live • Webhook ✓ • Kill-switch ✓
              </div>
            </div>
            <div className="mt-8 grid grid-cols-3 gap-4 max-w-[520px] border-t border-[#0F172A]/10 pt-6">
              {[
                { k: "ออเดอร์", v: "12,400+" },
                { k: "คืนเงิน", v: "<1.2%" },
                { k: "ส่งของ", v: "≤ 90s" },
              ].map((s) => (
                <div key={s.k}>
                  <div className="font-mono text-[10px] tracking-[0.14em] text-[#94A3B8]">{s.k}</div>
                  <div className="font-[DM_Serif_Display] text-[22px] leading-none text-[#0F172A] mt-1">{s.v}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Live preview — glass, not card-inside-card */}
          <div className="relative md:sticky md:top-[72px]">
            <div className="rounded-[16px] border border-[#0F172A]/10 bg-white shadow-[0_20px_60px_rgba(15,23,42,0.08)] overflow-hidden">
              <div className="h-9 flex items-center justify-between px-4 border-b border-[#0F172A]/5 bg-[#F8F6F3]">
                <span className="font-mono text-[10px] tracking-[0.14em] text-[#475569]">LIVE DASHBOARD — CEO VIEW</span>
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              </div>
              <div className="p-4 space-y-4">
                <div className="grid grid-cols-3 gap-3">
                  {[
                    { label: "ยอดวันนี้", value: "฿18,400", sub: "+12% vs เมื่อวาน" },
                    { label: "ออเดอร์ค้าง", value: "3", sub: "รอส่งของ" },
                    { label: "ROAS", value: "4.2×", sub: "7 วัน" },
                  ].map((m) => (
                    <div key={m.label} className="rounded-xl border border-[#0F172A]/5 bg-[#F8F6F3] p-3">
                      <div className="font-mono text-[10px] tracking-[0.1em] text-[#64748B]">{m.label}</div>
                      <div className="font-semibold text-[#0F172A] mt-1">{m.value}</div>
                      <div className="text-[11px] text-emerald-600">{m.sub}</div>
                    </div>
                  ))}
                </div>
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 flex items-start gap-3">
                  <div className="w-7 h-7 rounded-full bg-amber-500 text-white grid place-items-center text-xs">!</div>
                  <div>
                    <div className="text-sm font-semibold text-[#0F172A]">ขอนุมัติ: เพิ่มงบ Retarget +66%</div>
                    <div className="text-xs text-[#92400E] mt-0.5">ROAS 4.2 ติด 7 วัน — กด Approve ใน CEO Console ได้เลย</div>
                  </div>
                </div>
                <div className="flex gap-2 font-mono text-[11px]">
                  <span className="px-2 py-1 bg-[#0F172A] text-white">APPROVE</span>
                  <span className="px-2 py-1 border border-[#0F172A]/15">REJECT</span>
                  <span className="ml-auto text-[#64748B]">expires in 2 วัน</span>
                </div>
              </div>
              <div className="px-4 py-3 border-t border-[#0F172A]/5 flex items-center justify-between text-[11px] font-mono tracking-[0.08em] text-[#64748B]">
                <span>graxia-revenue-os.onrender.com • LIVE</span>
                <span className="text-emerald-600">● 200 OK</span>
              </div>
            </div>
            <div className="mt-3 text-center font-mono text-[10px] tracking-[0.12em] text-[#94A3B8]">ตัวอย่าง — ข้อมูลจริงหลังจ่ายเงินจะขึ้นแบบนี้</div>
          </div>
        </div>
      </section>

      {/* Spec — blueprint */}
      <section id="spec" className="mx-auto max-w-[1200px] px-6 md:px-10 py-8">
        <div className="border border-[#0F172A]/10 bg-white">
          <div className="grid md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-[#0F172A]/10">
            {[
              { n: "01", t: "ยิงแอด → ขออนุมัติ", d: "AI เสนอเพิ่มงบ/ปิดแคมเปญ — ต้อง Approve ก่อนยิงจริง กันงบไหล" },
              { n: "02", t: "จ่าย → ส่งของทันที", d: "Stripe webhook ยืนยันแล้วส่งไฟล์/สิทธิ์ใน 90s — ไม่ต้องคนเฝ้า" },
              { n: "03", t: "ตามลูกค้า + กันคืนเงิน", d: "อีเมลตามอัตโนมัติ + ledger ครบ + ปุ่มคืนเงินมี idempotency" },
            ].map((f) => (
              <div key={f.n} className="p-6">
                <div className="font-mono text-[11px] tracking-[0.14em] text-[#B45309]">{f.n}</div>
                <div className="font-semibold text-[#0F172A] mt-1">{f.t}</div>
                <div className="text-sm leading-6 text-[#475569] mt-1">{f.d}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing — 3 buttons */}
      <section id="pricing" className="mx-auto max-w-[1200px] px-6 md:px-10 py-10">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="font-mono text-[11px] tracking-[0.14em] text-[#B45309]">PRICING — 3 ปุ่ม จ่ายจริง Stripe Live</div>
            <h2 className="font-[DM_Serif_Display] text-[32px] md:text-[40px] leading-none tracking-[-0.02em] text-[#0F172A] mt-1">เลือกขนาดตามยอดขาย</h2>
          </div>
          <div className="font-mono text-xs text-[#64748B] border border-[#0F172A]/10 px-3 py-1.5 bg-white">ยกเลิกได้ทุกเดือน • ใบเสร็จอัตโนมัติ</div>
        </div>

        {error && <div className="mt-4 rounded-xl border border-red-200 bg-red-50 text-red-700 text-sm px-4 py-3">{error}</div>}

        <div className="mt-8 grid md:grid-cols-3 gap-6 items-stretch">
          {PRODUCTS.map((p) => {
            const isGrowth = p.accent === "brass"
            const isScale = p.accent === "ink"
            return (
              <div
                key={p.id}
                className={[
                  "relative flex flex-col rounded-[20px] border p-6 md:p-7",
                  isGrowth ? "bg-[#0F172A] text-white border-[#0F172A] shadow-[0_20px_60px_rgba(15,23,42,0.25)] md:-mt-3 md:mb-3" : "bg-white border-[#0F172A]/10",
                  isScale ? "bg-[#1C1917] text-[#F8F6F3] border-[#292524]" : "",
                ].join(" ")}
              >
                {p.badge && (
                  <div className={["absolute -top-3 left-6 px-2.5 py-1 text-[11px] font-mono tracking-[0.12em] text-white", isGrowth ? "bg-[#B45309]" : "bg-[#0F172A]"].join(" ")}>
                    {p.badge}
                  </div>
                )}
                <div className="flex items-baseline justify-between">
                  <div className={["font-mono text-[11px] tracking-[0.14em]", isGrowth || isScale ? "text-white/60" : "text-[#64748B]"].join(" ")}>{p.slug.toUpperCase()}</div>
                  <div className={["w-2 h-2 rounded-full", isGrowth ? "bg-amber-400" : isScale ? "bg-emerald-400" : "bg-[#0F172A]/20"].join(" ")} />
                </div>
                <div className="mt-2 font-[DM_Serif_Display] text-[28px] leading-none tracking-[-0.02em]">{p.name}</div>
                <div className="mt-1 text-sm leading-5 opacity-80">{p.promise}</div>
                <div className="mt-5 flex items-baseline gap-1">
                  <span className="font-[DM_Serif_Display] text-[36px] leading-none">{p.priceLabel}</span>
                  <span className={["font-mono text-xs", isGrowth || isScale ? "text-white/60" : "text-[#64748B]"].join(" ")}>{p.period}</span>
                </div>
                <div className={["mt-1 font-mono text-[11px]", isGrowth || isScale ? "text-white/50" : "text-[#94A3B8]"].join(" ")}>{p.subtext}</div>

                <ul className="mt-6 space-y-2.5">
                  {p.features.map((f) => (
                    <li key={f} className="flex gap-2 text-sm leading-5">
                      <span className={["mt-1 w-4 h-4 rounded-full grid place-items-center text-[10px] shrink-0", isGrowth ? "bg-white text-[#0F172A]" : isScale ? "bg-white/10 text-white" : "bg-[#0F172A] text-white"].join(" ")}>✓</span>
                      <span className={isGrowth || isScale ? "text-white/90" : "text-[#334155]"}>{f}</span>
                    </li>
                  ))}
                </ul>

                <button
                  onClick={() => checkout(p.id)}
                  disabled={loadingId === p.id}
                  className={[
                    "mt-8 w-full h-11 inline-flex items-center justify-center text-sm font-semibold transition-colors disabled:opacity-60",
                    isGrowth ? "bg-[#B45309] text-white hover:bg-[#92400E]" : isScale ? "bg-white text-[#1C1917] hover:bg-[#F8F6F3]" : "bg-[#0F172A] text-white hover:bg-[#1E293B]",
                  ].join(" ")}
                >
                  {loadingId === p.id ? "กำลังเปิด Stripe..." : `${p.cta} →`}
                </button>

                <div className={["mt-3 text-center font-mono text-[10px] tracking-[0.08em]", isGrowth || isScale ? "text-white/50" : "text-[#94A3B8]"].join(" ")}>
                  Stripe Live • ใบเสร็จอัตโนมัติ
                </div>
              </div>
            )
          })}
        </div>

        <div className="mt-6 rounded-xl border border-[#0F172A]/10 bg-[#F8F6F3] p-4 flex flex-wrap items-center justify-between gap-3">
          <div className="text-sm text-[#334155]">องค์กรใหญ่ 20M+/ปี — <span className="font-semibold text-[#0F172A]">Enterprise (Custom Quote)</span> ติดต่อทำ SLA 99.9% + ทีมดูแลเฉพาะ</div>
          <a href="mailto:hello@graxia.app?subject=Enterprise" className="h-9 px-4 inline-flex items-center border border-[#0F172A] text-sm font-semibold hover:bg-[#0F172A] hover:text-white transition-colors">
            ติดต่อ Enterprise
          </a>
        </div>
      </section>

      {/* Email modal */}
      {emailOpen && (
        <div className="fixed inset-0 z-50 grid place-items-center p-4 bg-[#0F172A]/40 backdrop-blur-sm">
          <div className="w-full max-w-[420px] rounded-2xl bg-white p-6 border border-[#0F172A]/10 shadow-xl">
            <div className="font-mono text-[11px] tracking-[0.14em] text-[#B45309]">CHECKOUT — STEP 1/1</div>
            <h3 className="font-semibold text-[#0F172A] mt-1">ใส่อีเมลเพื่อรับใบเสร็จ</h3>
            <p className="text-sm text-[#475569] mt-1">Stripe จะส่งใบเสร็จและลิงก์เข้าใช้งานไปที่อีเมลนี้</p>
            <input
              autoFocus
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              className="mt-4 w-full h-11 px-3 border border-[#0F172A]/15 rounded-xl text-sm outline-none focus:border-[#0F172A]"
            />
            <div className="mt-4 flex gap-2">
              <button onClick={() => setEmailOpen(null)} className="flex-1 h-11 border border-[#0F172A]/15 rounded-xl text-sm font-semibold">
                ยกเลิก
              </button>
              <button onClick={() => handleEmailSubmit(emailOpen)} className="flex-1 h-11 bg-[#B45309] text-white rounded-xl text-sm font-semibold hover:bg-[#92400E]">
                ไปหน้า Stripe →
              </button>
            </div>
            <div className="mt-3 text-center font-mono text-[11px] text-[#94A3B8]">Live — ตัดบัตรจริง</div>
          </div>
        </div>
      )}

      {/* FAQ — blueprint */}
      <section id="faq" className="mx-auto max-w-[1200px] px-6 md:px-10 py-10">
        <div className="border border-[#0F172A]/10 bg-white">
          <div className="p-6 border-b border-[#0F172A]/10 flex items-center justify-between">
            <h3 className="font-[DM_Serif_Display] text-[22px]">คำถามที่ถามบ่อย</h3>
            <span className="font-mono text-[11px] tracking-[0.12em] text-[#64748B]">SUPPORT — TH/EN</span>
          </div>
          <div className="divide-y divide-[#0F172A]/10">
            {[
              { q: "ยกเลิกได้ไหม? เก็บเงินยังไง?", a: "ได้ทุกเดือน — Stripe ตัดบัตรอัตโนมัติทุกเดือน กดยกเลิกใน Billing Portal ได้ทันที ไม่มีผูกมัด" },
              { q: "ต่างจากจ้างแอดมินยังไง?", a: "Revenue OS ขออนุมัติก่อนยิงงบทุกครั้ง กันงบไหล — แอดมินทำตามคนสั่ง แต่ระบบทำตาม ROAS จริง พร้อม ledger ครบ" },
              { q: "ต้องย้ายร้านไหม?", a: "ไม่ต้อง — ต่อ Shopee/Shopify/TikTok เดิมได้เลย ระบบซิงก์สต็อกกลางให้" },
              { q: "Scale ต่างจาก Growth ยังไง?", a: "Scale ได้ SLA 99.5% + Onboarding ตั้งค่าให้ 1 เดือน + Incident เฝ้า 24 ชม. เหมาะกับร้าน 5–20M/ปี" },
            ].map((f) => (
              <details key={f.q} className="group p-6 open:bg-[#F8F6F3]">
                <summary className="list-none flex items-center justify-between cursor-pointer">
                  <span className="font-semibold text-[#0F172A]">{f.q}</span>
                  <span className="w-7 h-7 rounded-full border border-[#0F172A]/15 grid place-items-center group-open:rotate-45 transition-transform">+</span>
                </summary>
                <p className="text-sm leading-6 text-[#475569] mt-3">{f.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* Footer — blueprint stamp */}
      <footer className="mx-auto max-w-[1200px] px-6 md:px-10 pb-10">
        <div className="border border-[#0F172A]/10 bg-[#0F172A] text-white p-6 flex flex-wrap items-center justify-between gap-4">
          <div className="font-mono text-[11px] tracking-[0.14em] text-white/60">© 2026 GRAXIA — REVENUE OS • THAILAND • LIVE</div>
          <div className="flex items-center gap-3 text-xs font-mono">
            <a href="/terms" className="text-white/60 hover:text-white">
              Terms
            </a>
            <span className="text-white/20">/</span>
            <a href="/privacy" className="text-white/60 hover:text-white">
              Privacy
            </a>
            <span className="px-2 py-1 bg-white text-[#0F172A]">STRIPE LIVE ✓</span>
          </div>
        </div>
      </footer>
    </div>
  )
}

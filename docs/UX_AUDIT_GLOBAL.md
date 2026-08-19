# Global UX/UI Audit — Ai Factory (Graxia OS storefront)

**วันที่:** 2026-08-13 · **Product:** Ai Factory — ร้านสินค้าดิจิทัล AI ภาษาไทย (prompts/templates/courses)
**Platform:** Web responsive (React 18 + Vite + Tailwind + Vercel serverless)
**URL:** https://graxia-os-funnel.vercel.app
**Markets:** ไทย (หลัก) + EN (global) · **Languages:** TH/EN · **ธีม:** light violet (#F5F4FA / violet #9E7AFF→pink #FE8BBB)
**หลักฐาน:** code audit (subagent — file:line quotes) + live browser (Playwright TH/EN, 375px mobile, 200% zoom)

---

## 1. Executive Summary

The storefront has a coherent light-violet visual system, solid responsive behavior (no horizontal overflow at 375px or 200% zoom — verified live), and good Thai font coverage (Sarabun/Prompt). The biggest risks are not visual but systemic: **4 of 8 public pages have zero i18n** (Login/Register/CheckoutSuccess/DeliveryAccess are 100% hardcoded EN), **the product catalog is inverted** (base data is Thai; EN users see Thai product names — verified live: h1 renders "AI Prompt Pack เริ่มต้น (50 Prompts)"), and **there is no legal layer at all** — no Terms/Privacy pages, no cookie banner, no PDPA consent despite collecting emails (critical for the Thai market). Accessibility is workable-but-friction: unlabeled inputs, icon-only buttons without aria-label, and one page missing h1. Biggest wins: the violet theme is consistent, marquee/spotlight/pill-nav motion is polished, and checkout labels + focus rings are in place.

## 2. Findings Table

| Severity | Dim | Location | Issue | Why it matters globally | Recommendation |
|---|---|---|---|---|---|
| 🔴 | 5 Localization | Login.tsx:48,64,81,97… | 100% hardcoded EN; brand says "Log in to **Graxia OS**" (wrong product) | TH users (primary market) get English auth; wrong brand erodes trust | Route all 4 pages through `t()`; fix brand string to Ai Factory |
| 🔴 | 5 Localization | Register.tsx:24-142 | 100% hardcoded EN (Full name/Email/Password/errors) | Registration locked for TH users | i18n-ize |
| 🔴 | 5 Localization | CheckoutSuccess.tsx:32-92 | 100% hardcoded EN; "Next Instructions / Check Your Email Inbox / Stripe Session ID" | Post-purchase moment is the highest-trust moment; EN-only breaks TH flow | i18n-ize |
| 🔴 | 5 Localization | DeliveryAccessPage.tsx:38-198 | 100% hardcoded EN + typo "Exclusive Content Content:" (L169) | Delivery is the product moment; TH users can't read it | i18n-ize + fix typo |
| 🔴 | 4 i18n | products.ts:57,82,107 vs products-th.ts:8… | Catalog base data is **Thai**; products-th.ts keys (`prod-001…`) never match product UUIDs → `getThProduct` always null; EN users see Thai names (verified live) | EN market sees untranslated names; Thai file is dead code | Fix mapping: name EN as base, Thai in products-th keyed by UUID |
| 🔴 | 9 Legal | App.tsx:54-92 + footer LandingPage:684-687 | **No Terms/Privacy/Refund pages** (footer items are inert `<span>`s); **no cookie/consent banner**; funnel collects emails (checkout L114, lead magnet L143-148, popup L46-54) with zero consent | **PDPA (ไทย) requires explicit consent** — legal exposure in primary market; GDPR/EAA equivalent for EN | Add Privacy/Terms pages + consent notice on email capture + footer links |
| 🔴 | 9 Legal | translations.ts:84 "We never store card details" + SocialProofPopup.tsx:7 "Uses fake data for demo" | Fake purchase popups + no data-processing disclosure | Fabricated trust signals = deceptive; legal risk | Replace with real events (funnel API has conversion events) or remove |
| 🟠 | 5 Localization | All copy | Stripe-only payment copy; **zero PromptPay/QR** mentions (grep 0) | THB store without PromptPay misses dominant Thai rail; conversion + trust gap | Add PromptPay/QR to trust copy (even if via Stripe) |
| 🟠 | 3 A11y | StorePage:160,170; PublicProductPage:460-463; StoreProductPage:212-213 | 5 inputs placeholder-only (no label/aria-label) | Screen-reader users can't identify fields (WCAG 1.3.1/4.1.2) | Add `<label>` or aria-label |
| 🟠 | 3 A11y | StorePage:163; ExitIntentPopup:67; SocialProofPopup:117 | Icon-only buttons without aria-label (clear search, close ×2) | SR users can't act | aria-label="ล้าง/ปิด/Close" |
| 🟠 | 3 A11y | DeliveryAccessPage:113 | Page has no h1 (starts at h2) | Broken heading hierarchy (WCAG 1.3.1) | Add h1 |
| 🟠 | 3 A11y | products.ts:65,90,115 `coverImageUrl: ""` | All product images empty → broken img (alt never visible) | Visual + a11y failure on every card | Provide images or hide img with placeholder |
| 🟠 | 7 Perf | — | No LCP/INP budget measured; 3 font CSS loads; images empty | Low-end Android + metered data markets | Add image assets + lazy-load; measure CWV |
| 🟠 | 8 Content | LandingPage:526-530 testimonials | Testimonial strings contain **Russian** inside Thai block (` инвестицияที่ดีที่สุด`); identical TH/EN branch (L526) | Broken L10n in core marketing copy | Fix copy, differentiate TH/EN |
| 🟠 | 4 i18n | LandingPage:248,261 `w-[336px] h-[72px]` CTAs | Fixed-size 2-line CTAs — German/Russian text wraps/clips | Text expansion breaks CTAs | Use `min-w`/auto-height or clamp with ellipsis |
| 🟠 | 4 i18n | LandingPage:612; PublicProductPage:536; StoreProductPage:275 `max-h-96` + overflow-hidden | FAQ answers >384px get clipped | Long localized answers truncated | Use auto height or scrollable panel |
| 🟠 | 9 Legal | PublicProductPage:38 fake countdown `useState({hours:23,…})` resets each load | Deceptive urgency timer | Fake scarcity = deceptive practice (legal/ethical) | Remove or use real time window |
| 🟡 | 4 i18n | index.html:7 `<title>Graxia OS — AI-Powered Trading Platform` | Wrong product title + static `<html lang="en">`, no `dir` switching, `document.title` not localized | SEO + SR + L10n broken | Set lang per locale, fix title |
| 🟡 | 4 i18n | products.ts:223-242 `formatPrice`/`formatSalesCount` | Formatting keyed by currency not UI locale; `"K+"` hardcoded; `toLocaleString()` uses browser locale (LandingPage:72, etc.) | Number/currency mismatch vs UI language | Use UI locale; localize "K+" |
| 🟡 | 6 Responsive | Playwright live | Mobile 375px: no horizontal overflow ✅; but primary CTA `a.bg-secondary` count=0 on mobile — needs re-check | Possible CTA hidden on mobile | Verify + fix if hidden |
| 🟡 | 3 A11y | StorePage:246,250,256,267 + others | `text-[10px]`/`text-[9px]` micro-labels + `uppercase tracking-wider` | Readability fails for low-vision/older users | Bump to 11-12px min |
| 🟡 | 2 Visual | LandingPage:525-530 avatars `bg-amber-500` etc. | Amber/raw palette leftovers in avatars (violet theme has 1.5:1 amber) | Mixed palette after theme change | Remap to violet/pink |
| 🟡 | 4 i18n | LandingPage:107 ml-0.5 caret, StorePage:212 ml-2, -space-x-2 (L275), ArrowRight CTAs | Physical properties + directional glyphs — RTL breaks | Arabic expansion future | Use logical props (`ms-`/`text-start`) when RTL planned |
| 🟢 | 1 Usability | PublicProductPage:95,122,126,136,155 | `alert()` for errors instead of inline states | Crude UX, blocks on mobile | Inline error messages |
| 🟢 | 3 A11y | ExitIntentPopup:62,135 | Popup not `role="dialog"`/`aria-modal`; `autoFocus` hostile on mobile | SR + keyboard confusion | Add dialog roles; drop autoFocus |
| 🟢 | 5 Localization | fonts (tailwind.config.js:50-56) | Thai ✓ (Sarabun/Prompt); no CJK/Arabic/Cyrillic designed fallback | Future markets fall to system fonts | Add per-script stacks when expanding |
| 🟢 | 1 Usability | StoreProductPage:132,137,167,180,301 | "reviews"/"Updated"/"-day guarantee" unlocalized in TH mode | Inconsistent L10n in product page | Route through t() |

## 3. Scorecard (1–5)

| Dim | Score | Justification (evidence-based) |
|---|---|---|
| 1. Usability & Interaction | 3 | Flows work; alert() errors, fake countdown, dead-end CheckoutSuccess (no back), popups non-modal |
| 2. Visual & Information Design | 4 | Consistent violet system, hierarchy good; micro-text 9-10px + a few amber leftovers |
| 3. Accessibility | 2 | 5 unlabeled inputs, 3 aria-less icon buttons, 1 page no h1, broken imgs, micro-text; focus rings + checkout label good |
| 4. Internationalization | 2 | 4/8 pages 0% i18n; catalog inverted (EN sees Thai); fixed CTAs/FAQ clip; lang/dir not switched; currency not UI-locale |
| 5. Localization & Culture | 2 | No PDPA consent, no PromptPay, wrong brand in Login, Russian text in TH copy, fake social proof |
| 6. Responsive & Cross-Device | 4 | Verified: no overflow at 375px or 200% zoom; pill nav works; mobile CTA needs re-check |
| 7. Performance Perception | 3 | Skeletons exist; empty images; no CWV budget measured |
| 8. Content & Microcopy | 3 | Good t() coverage on 4 pages; typos ("Content Content:"), mixed hardcoded strings, English-only errors |
| 9. Trust, Compliance & Legal | 1 | **No Terms/Privacy/cookie/consent anywhere** — PDPA-critical; fake trust data; fake countdown |
| 10. Brand & Cross-Market | 3 | Violet system consistent (globally fine); Login "Graxia OS" + html title wrong product (locally broken) |

**Overall: 2.7/5 — workable visually, not market-ready for TH (legal) or EN (i18n).**

## 4. Quick Wins (days) vs Strategic Fixes (system)

**Quick Wins:**
1. i18n-ize Login/Register (reuse existing t() keys — AuthShell exists)
2. i18n-ize CheckoutSuccess + DeliveryAccess (post-purchase + delivery = highest trust moments)
3. Fix catalog mapping (products-th keyed by UUID) — EN names correct instantly
4. Add aria-label to 3 icon buttons + labels to 5 inputs
5. Fix typo "Content Content:", Russian-in-TH string, wrong brand "Graxia OS" → "Ai Factory"
6. Remove/disable fake countdown + fake social-proof data (or wire to real funnel events)
7. Add `lang` switch on `<html>` per locale + fix document.title

**Strategic Fixes:**
1. **Legal layer:** Privacy Policy + Terms pages (PDPA-compliant consent on email capture; GDPR note for EN) + footer links — required before scaling TH
2. **Local payments:** PromptPay/QR messaging; Stripe payment method config
3. **L10n system hardening:** move ALL strings to t(); UI-locale-based number/currency/date formatting; text-expansion-safe layouts (auto-height FAQ, min-width CTAs)
4. **Accessibility pass:** h1 per page, dialog roles for popups, 12px minimum text, image assets for products
5. **RTL-ready primitives** (logical properties) when Arabic/global expansion planned
6. **CWV budget + image assets** for low-end Android/metered-data markets

## 5. Open Questions

1. **Target-market priority**: is TH the only go-to-market for the next 6 months, or is EN/global concurrent? (Affects PDPA urgency vs EAA/GDPR.)
2. **Product images**: are cover images coming from a CDN/asset pipeline, or should we build placeholder gradients (violet-themed) now?
3. **Legal ownership**: who owns Terms/Privacy copy — need Thai counsel for PDPA?
4. **Payments**: is PromptPay via Stripe (Standard) acceptable, or does the store need PromptPay direct (Omise/KREDS) later?
5. **Fake social proof**: replace with real funnel conversion events (available in API) or remove entirely?
6. **Mobile CTA check**: live check showed primary CTA count 0 at 375px — needs a follow-up verification to confirm visibility (possibly below-the-fold or selector timing).

---
*Audit method: code audit (subagent, file:line evidence) + live browser verification (Playwright: TH/EN, 375px, 200% zoom, computed colors). Findings only where evidence exists; unverified items are in Open Questions.*

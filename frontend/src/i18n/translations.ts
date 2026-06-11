export type Locale = "th" | "en";

// NOTE: Use "||" as a delimiter in translation values where the part after "||"
// should be highlighted with a gradient. E.g. "features.title" splits on "||"
// and the second segment gets gradient text styling in LandingPage.tsx.

export const translations: Record<Locale, Record<string, string>> = {
  en: {
    // Brand
    "brand.name": "Ai Factory",
    "brand.tagline": "AI Tools for Freelancers & Students",
    "brand.description": "Premium digital products, templates, and courses for creators, developers, and entrepreneurs.",
    "brand.author": "Ai Factory",

    // Nav
    "nav.features": "Features",
    "nav.products": "Browse Products",
    "nav.testimonials": "Testimonials",
    "nav.pricing": "Pricing",
    "nav.faq": "FAQ",
    "nav.signIn": "Sign in",
    "nav.getStarted": "Get Started",
    "nav.dashboard": "Dashboard",
    "nav.secureCheckout": "Secure Checkout",

    // Hero
    "hero.badge": "Trusted by 50,000+ creators worldwide",
    "hero.title1": "Premium AI Tools",
    "hero.title2": "That Actually Work",
    "hero.subtitle": "Browse 200+ battle-tested templates, courses, and tools built by experts.\nEvery product is designed to save you time, make you money, or both.",
    "hero.cta1": "Browse All Products",
    "hero.cta2": "See How It Works",
    "hero.customers": "happy customers",
    "hero.rating": "average rating",
    "hero.guarantee": "30-day money-back guarantee",

    // Stats
    "stats.sold": "Products Sold",
    "stats.customers": "Happy Customers",
    "stats.rating": "Avg Rating",
    "stats.revenue": "Revenue Generated",

    // Featured
    "featured.badge": "Bestsellers",
    "featured.title": "Featured Products",
    "featured.subtitle": "Our most popular products, loved by thousands of creators, developers, and entrepreneurs.",
    "featured.viewAll": "View All {count} Products",
    "featured.sold": "sold",

    // Categories
    "categories.badge": "Browse by Category",
    "categories.title": "Find What You Need",
    "cat.ai-automation": "AI & Automation",
    "cat.productivity": "Productivity",
    "cat.design": "Design Assets",
    "cat.developer": "Developer Tools",
    "cat.marketing": "Marketing",
    "cat.finance": "Finance & Tax",
    "cat.education": "Education",
    "cat.health": "Health & Wellness",
    "cat.content": "Content Creation",
    "catDesc.ai-automation": "AI prompts, workflows, and automation templates",
    "catDesc.productivity": "Notion templates, dashboards, and life OS systems",
    "catDesc.design": "UI kits, icons, templates, and brand assets",
    "catDesc.developer": "Code templates, boilerplates, and component libraries",
    "catDesc.marketing": "Swipe files, ad templates, and copywriting frameworks",
    "catDesc.finance": "Budget trackers, tax templates, and financial dashboards",
    "catDesc.education": "Courses, guides, and learning resources",
    "catDesc.health": "Fitness plans, meal prep, and wellness trackers",
    "catDesc.content": "Video templates, social media, and creator tools",

    // Features
    "features.badge": "Why Ai Factory",
    "features.title": "Everything You Need to ||Succeed Faster",
    "features.instant.title": "Instant Delivery",
    "features.instant.desc": "Get immediate access after purchase. No waiting, no shipping. Start using your product within seconds.",
    "features.quality.title": "Expert-Crafted Quality",
    "features.quality.desc": "Every product is built by industry experts and tested by real users. Only battle-tested, production-ready templates.",
    "features.roi.title": "Proven ROI",
    "features.roi.desc": "Our products have helped generate over $12M in revenue for our customers. Templates that actually move the needle.",
    "features.updates.title": "Lifetime Updates",
    "features.updates.desc": "Products are continuously improved. Get all future updates free — no subscription, no hidden fees.",
    "features.secure.title": "Secure Checkout",
    "features.secure.desc": "256-bit encryption via Stripe. Your payment information is always protected. We never store card details.",
    "features.guarantee.title": "30-Day Guarantee",
    "features.guarantee.desc": "Not satisfied? Full refund within 30 days, no questions asked. We're confident you'll love our products.",

    // How It Works
    "howItWorks.badge": "Simple Process",
    "howItWorks.title": "3 Steps to Get Started",
    "howItWorks.step1.title": "Browse & Choose",
    "howItWorks.step1.desc": "Explore our curated collection of digital products. Filter by category, read reviews, and find the perfect match for your needs.",
    "howItWorks.step2.title": "Secure Checkout",
    "howItWorks.step2.desc": "Complete your purchase in seconds with our Stripe-powered checkout. Apple Pay, Google Pay, and all major cards accepted.",
    "howItWorks.step3.title": "Instant Access",
    "howItWorks.step3.desc": "Receive your download link instantly via email. Start using your product immediately — most include setup guides and tutorials.",

    // Testimonials
    "testimonials.badge": "Testimonials",
    "testimonials.title": "Loved by Creators Worldwide",

    // Pricing
    "pricing.badge": "Fair Pricing",
    "pricing.title": "One-Time Purchase. Lifetime Access.",
    "pricing.subtitle": "No subscriptions, no recurring fees, no hidden costs. Pay once, use forever, and get all future updates free.",
    "pricing.quickWins": "Quick Wins",
    "pricing.proTools": "Pro Tools",
    "pricing.premium": "Premium",
    "pricing.guarantee": "30-day money-back guarantee on every product",

    // FAQ
    "faq.badge": "FAQ",
    "faq.title": "Frequently Asked Questions",
    "faq.q1": "What exactly do I get after purchase?",
    "faq.a1": "You receive instant access to digital files including Notion templates, PDF guides, video tutorials, and source code — depending on the product. Everything is delivered via a secure download link sent to your email immediately after payment.",
    "faq.q2": "How does the 30-day money-back guarantee work?",
    "faq.a2": "If you're not satisfied with your purchase for any reason, email us within 30 days and we'll issue a full refund. No questions asked.",
    "faq.q3": "Can I use these products for commercial purposes?",
    "faq.a3": "Yes! All products come with a commercial license. You can use them in your business, for client work, and modify them to fit your needs.",
    "faq.q4": "How are the products delivered?",
    "faq.a4": "After successful payment via Stripe, you'll receive an email with a secure download link. Most products include Notion template links, downloadable files, and video access.",
    "faq.q5": "Do I get free updates?",
    "faq.a5": "Yes! All products include lifetime updates. When we improve templates, add new content, or fix issues, you'll receive the updated version at no extra cost.",
    "faq.q6": "What payment methods do you accept?",
    "faq.a6": "We accept all major credit cards, debit cards, and digital wallets through Stripe. Payments are processed securely with 256-bit encryption.",

    // CTA
    "cta.title": "Ready to Level Up?",
    "cta.subtitle": "Join 50,000+ creators who are building faster, working smarter, and earning more with our digital products.",
    "cta.button": "Start Shopping",

    // Footer
    "footer.products": "Products",
    "footer.resources": "Resources",
    "footer.legal": "Legal",
    "footer.blog": "Blog",
    "footer.helpCenter": "Help Center",
    "footer.affiliate": "Affiliate Program",
    "footer.becomeCreator": "Become a Creator",
    "footer.terms": "Terms of Service",
    "footer.privacy": "Privacy Policy",
    "footer.refund": "Refund Policy",
    "footer.license": "License Agreement",
    "footer.copyright": "© 2026 Ai Factory. All rights reserved.",
    "footer.secured": "Secured by Stripe · 256-bit encryption",

    // Store Page
    "store.title": "All Products",
    "store.search": "Search products, templates, categories...",
    "store.noResults": "No products found",
    "store.noResultsDesc": "Try adjusting your search or filter to find what you're looking for.",
    "store.clearAll": "Clear all filters",
    "store.clearFilter": "Clear filter",
    "store.showing": "Showing",
    "store.products": "products",
    "store.sortPopular": "Most Popular",
    "store.sortNewest": "Newest",
    "store.sortPriceLow": "Price: Low to High",
    "store.sortPriceHigh": "Price: High to Low",
    "store.sortRating": "Highest Rated",
    "store.trust1": "30-day money-back guarantee",
    "store.trust2": "Instant digital delivery",
    "store.trust3": "Lifetime free updates",
    "store.allProducts": "All Products",

    // Product Page
    "product.backToStore": "Back to Store",
    "product.buyNow": "Buy Now",
    "product.premiumAccess": "Premium Access",
    "product.oneTime": "One-time payment · Instant delivery",
    "product.whatsIncluded": "What's Included",
    "product.customersSay": "What Customers Say",
    "product.youllReceive": "What You'll Receive",
    "product.faqTitle": "Frequently Asked Questions",
    "product.readyToStart": "Ready to Get Started?",
    "product.joinCustomers": "customers who are already using this product.",
    "product.getInstantAccess": "Get Instant Access",
    "product.instantAccess": "Instant access after payment",
    "product.stripeEncrypted": "256-bit Stripe encryption",
    "product.moneyBack": "money-back guarantee",
    "product.happyCustomers": "happy customers",
    "product.secureEncrypted": "Secure, encrypted checkout",
    "product.limitedOffer": "Limited Time Offer Ends In:",
    "product.freeSample": "Get a Free Sample First",
    "product.freeSampleDesc": "Preview the quality before you buy.",
    "product.getFreeSample": "Get Free Sample",
    "product.deliveryEmail": "Delivery Email",
    "product.unlockAccess": "Unlock Access Now",
    "product.connecting": "Connecting to Stripe...",
    "product.notFound": "Product Not Found",
    "product.notFoundDesc": "The product you're looking for doesn't exist.",
    "product.browseStore": "Browse Store",

    // Language
    "lang.switch": "TH",
  },

  th: {
    // Brand
    "brand.name": "Ai Factory",
    "brand.tagline": "เครื่องมือ AI สำหรับ Freelancer และ นักศึกษา",
    "brand.description": "สินค้าดิจิทัลระดับพรีเมียม เทมเพลต และคอร์สเรียน สำหรับครีเอเตอร์ นักพัฒนา และผู้ประกอบการ",
    "brand.author": "Ai Factory",

    // Nav
    "nav.features": "ฟีเจอร์",
    "nav.products": "ดูสินค้าทั้งหมด",
    "nav.testimonials": "รีวิว",
    "nav.pricing": "ราคา",
    "nav.faq": "คำถามที่พบบ่อย",
    "nav.signIn": "เข้าสู่ระบบ",
    "nav.getStarted": "เริ่มต้นใช้งาน",
    "nav.dashboard": "แดชบอร์ด",
    "nav.secureCheckout": "ชำระเงินปลอดภัย",

    // Hero
    "hero.badge": "ได้รับความไว้วางใจจากครีเอเตอร์กว่า 50,000+ คนทั่วโลก",
    "hero.title1": "เครื่องมือ AI ระดับพรีเมียม",
    "hero.title2": "ที่ใช้ได้จริง",
    "hero.subtitle": "เทมเพลต คอร์สเรียน และเครื่องมือกว่า 200+ ชิ้น ที่ผ่านการทดสอบมาแล้ว\nทุกสินค้าออกแบบมาเพื่อประหยัดเวลา สร้างรายได้ หรือทั้งสองอย่าง",
    "hero.cta1": "ดูสินค้าทั้งหมด",
    "hero.cta2": "ดูวิธีการทำงาน",
    "hero.customers": "ลูกค้าที่พอใจ",
    "hero.rating": "คะแนนเฉลี่ย",
    "hero.guarantee": "รับประกันคืนเงิน 30 วัน",

    // Stats
    "stats.sold": "สินค้าที่ขายแล้ว",
    "stats.customers": "ลูกค้าที่พอใจ",
    "stats.rating": "คะแนนเฉลี่ย",
    "stats.revenue": "รายได้ที่สร้างให้ลูกค้า",

    // Featured
    "featured.badge": "ขายดีที่สุด",
    "featured.title": "สินค้าแนะนำ",
    "featured.subtitle": "สินค้าขายดีที่สุดของเรา ได้รับความนิยมจากครีเอเตอร์ นักพัฒนา และผู้ประกอบการหลายพันคน",
    "featured.viewAll": "ดูสินค้าทั้งหมด {count} ชิ้น",
    "featured.sold": "ขายแล้ว",

    // Categories
    "categories.badge": "เลือกตามหมวดหมู่",
    "categories.title": "ค้นหาสิ่งที่คุณต้องการ",
    "cat.ai-automation": "AI และระบบอัตโนมัติ",
    "cat.productivity": "ผลิตภาพ",
    "cat.design": "สินค้าออกแบบ",
    "cat.developer": "เครื่องมือนักพัฒนา",
    "cat.marketing": "การตลาด",
    "cat.finance": "การเงินและภาษี",
    "cat.education": "การศึกษา",
    "cat.health": "สุขภาพและสุขภาวะ",
    "cat.content": "การสร้างเนื้อหา",
    "catDesc.ai-automation": "เทมเพลต AI สำเร็จรูป ระบบอัตโนมัติ และเวิร์กโฟลว์",
    "catDesc.productivity": "เทมเพลต Notion แดชบอร์ด และระบบจัดการชีวิต",
    "catDesc.design": "ชุด UI ไอคอน เทมเพลต และทรัพยากรการออกแบบ",
    "catDesc.developer": "โค้ดเทมเพลต บอยเลอร์เพลต และไลบรารีคอมโพเนนต์",
    "catDesc.marketing": "ไฟล์โฆษณา เทมเพลต Ads และกรอบงานเขียนขาย",
    "catDesc.finance": "ตัวติดตามงบประมาณ เทมเพลตภาษี และแดชบอร์ดการเงิน",
    "catDesc.education": "คอร์สเรียน คู่มือ และทรัพยากรการเรียนรู้",
    "catDesc.health": "แผนออกกำลังกาย เมนูอาหาร และเครื่องมือสุขภาพ",
    "catDesc.content": "เทมเพลตวิดีโอ โซเชียลมีเดีย และเครื่องมือครีเอเตอร์",
    "features.badge": "ทำไมต้อง Ai Factory",
    "features.title": "ทุกอย่างที่คุณต้องการเพื่อ||ประสบความสำเร็จเร็วขึ้น",
    "features.instant.title": "ส่งมอบทันที",
    "features.instant.desc": "เข้าถึงสินค้าได้ทันทีหลังชำระเงิน ไม่ต้องรอ ไม่ต้องจัดส่ง เริ่มใช้งานได้ภายในไม่กี่วินาที",
    "features.quality.title": "คุณภาพโดยผู้เชี่ยวชาญ",
    "features.quality.desc": "ทุกสินค้าสร้างโดยผู้เชี่ยวชาญในวงการ และทดสอบโดยผู้ใช้จริง เทมเพลตที่ผ่านการใช้งานจริงเท่านั้น",
    "features.roi.title": "ROI ที่พิสูจน์แล้ว",
    "features.roi.desc": "สินค้าของเราช่วยสร้างรายได้มากกว่า $12M ให้ลูกค้า เทมเพลตที่สร้างผลลัพธ์จริง",
    "features.updates.title": "อัปเดตฟรีตลอดชีพ",
    "features.updates.desc": "สินค้าได้รับการพัฒนาอย่างต่อเนื่อง อัปเดตทุกเวอร์ชันฟรี — ไม่มีค่าสมัครสมาชิก ไม่มีค่าซ่อน",
    "features.secure.title": "ชำระเงินปลอดภัย",
    "features.secure.desc": "เข้ารหัส 256 บิตผ่าน Stripe ข้อมูลการชำระเงินของคุณปลอดภัยเสมอ เราไม่เก็บข้อมูลบัตรเครดิต",
    "features.guarantee.title": "รับประกัน 30 วัน",
    "features.guarantee.desc": "ไม่พอใจ? คืนเงินเต็มจำนวนภายใน 30 วัน ไม่มีคำถาม เรามั่นใจว่าคุณจะพอใจกับสินค้าของเรา",

    // How It Works
    "howItWorks.badge": "ขั้นตอนง่ายๆ",
    "howItWorks.title": "3 ขั้นตอนเพื่อเริ่มต้น",
    "howItWorks.step1.title": "เลือกดูสินค้า",
    "howItWorks.step1.desc": "ค้นหาสินค้าดิจิทัลที่คัดสรรมาแล้ว กรองตามหมวดหมู่ อ่านรีวิว และค้นหาสินค้าที่เหมาะกับความต้องการของคุณ",
    "howItWorks.step2.title": "ชำระเงินปลอดภัย",
    "howItWorks.step2.desc": "ชำระเงินให้เสร็จในไม่กี่วินาทีด้วย Stripe รองรับ Apple Pay, Google Pay และบัตรเครดิตทุกประเภท",
    "howItWorks.step3.title": "เข้าถึงทันที",
    "howItWorks.step3.desc": "รับลิงก์ดาวน์โหลดผ่านอีเมลทันที เริ่มใช้งานสินค้าได้เลย — ส่วนใหญ่มีคู่มือการตั้งค่าและวิดีโอสอน",

    // Testimonials
    "testimonials.badge": "รีวิวจากลูกค้า",
    "testimonials.title": "ได้รับความรักจากครีเอเตอร์ทั่วโลก",

    // Pricing
    "pricing.badge": "ราคาเป็นธรรม",
    "pricing.title": "จ่ายครั้งเดียว เข้าถึงตลอดชีพ",
    "pricing.subtitle": "ไม่มีค่า subscription ไม่มีค่าธรรมเนียมรายเดือน ไม่มีค่าซ่อน จ่ายครั้งเดียว ใช้ได้ตลอด และรับอัปเดตฟรีทุกเวอร์ชัน",
    "pricing.quickWins": "เริ่มต้นเร็ว",
    "pricing.proTools": "เครื่องมือโปร",
    "pricing.premium": "ระดับพรีเมียม",
    "pricing.guarantee": "รับประกันคืนเงิน 30 วัน ทุกสินค้า",

    // FAQ
    "faq.badge": "คำถามที่พบบ่อย",
    "faq.title": "คำถามที่พบบ่อย",
    "faq.q1": "หลังซื้อแล้วจะได้รับอะไรบ้าง?",
    "faq.a1": "คุณจะได้รับสินค้าดิจิทัลทันที รวมถึงเทมเพลต Notion คู่มือ PDF วิดีโอสอน และซอร์สโค้ด — ขึ้นอยู่กับสินค้า ทุกอย่างส่งผ่านลิงก์ดาวน์โหลดปลอดภัยไปยังอีเมลของคุณทันทีหลังชำระเงิน",
    "faq.q2": "การรับประกันคืนเงิน 30 วันทำงานอย่างไร?",
    "faq.a2": "หากคุณไม่พอใจกับสินค้าด้วยเหตุผลใดก็ตาม อีเมลมาหาเราภายใน 30 วัน เราจะคืนเงินเต็มจำนวน ไม่มีคำถาม",
    "faq.q3": "สามารถใช้สินค้าในเชิงพาณิชย์ได้หรือไม่?",
    "faq.a3": "ได้! ทุกสินค้ามีลิขสิทธิ์การใช้งานเชิงพาณิชย์ คุณสามารถใช้ในธุรกิจ ทำงานให้ลูกค้า และดัดแปลงตามความต้องการ",
    "faq.q4": "สินค้าจัดส่งอย่างไร?",
    "faq.a4": "หลังชำระเงินผ่าน Stripe สำเร็จ คุณจะได้รับอีเมลพร้อมลิงก์ดาวน์โหลดปลอดภัย สินค้าส่วนใหญ่รวมลิงก์เทมเพลต Notion ไฟล์ดาวน์โหลด และวิดีโอ",
    "faq.q5": "ได้รับอัปเดตฟรีหรือไม่?",
    "faq.a5": "ใช่! ทุกสินค้ารวมอัปเดตตลอดชีพ เมื่อเราปรับปรุงเทมเพลต เพิ่มเนื้อหาใหม่ หรือแก้ไขปัญหา คุณจะได้รับเวอร์ชันอัปเดตโดยไม่มีค่าใช้จ่ายเพิ่มเติม",
    "faq.q6": "รองรับวิธีชำระเงินใดบ้าง?",
    "faq.a6": "เรารองรับบัตรเครดิต บัตรเดบิต และกระเป๋าเงินดิจิทัลทุกประเภทผ่าน Stripe การชำระเงินเข้ารหัส 256 บิตอย่างปลอดภัย",

    // CTA
    "cta.title": "พร้อมที่จะก้าวไปอีกขั้นหรือยัง?",
    "cta.subtitle": "เข้าร่วมครีเอเตอร์กว่า 50,000+ คนที่สร้างสรรค์ได้เร็วขึ้น ทำงานฉลาดขึ้น และมีรายได้มากขึ้น",
    "cta.button": "เริ่มช็อปปิ้ง",

    // Footer
    "footer.products": "สินค้า",
    "footer.resources": "แหล่งข้อมูล",
    "footer.legal": "กฎหมาย",
    "footer.blog": "บล็อก",
    "footer.helpCenter": "ศูนย์ช่วยเหลือ",
    "footer.affiliate": "โปรแกรม affiliate",
    "footer.becomeCreator": "เป็นครีเอเตอร์",
    "footer.terms": "เงื่อนไขการใช้บริการ",
    "footer.privacy": "นโยบายความเป็นส่วนตัว",
    "footer.refund": "นโยบายคืนเงิน",
    "footer.license": "ข้อตกลงลิขสิทธิ์",
    "footer.copyright": "© 2026 Ai Factory สงวนลิขสิทธิ์",
    "footer.secured": "ชำระเงินปลอดภัยผ่าน Stripe · เข้ารหัส 256 บิต",

    // Store Page
    "store.title": "สินค้าทั้งหมด",
    "store.search": "ค้นหาสินค้า เทมเพลต หมวดหมู่...",
    "store.noResults": "ไม่พบสินค้า",
    "store.noResultsDesc": "ลองปรับการค้นหาหรือตัวกรองเพื่อค้นหาสิ่งที่คุณต้องการ",
    "store.clearAll": "ล้างตัวกรองทั้งหมด",
    "store.clearFilter": "ล้างตัวกรอง",
    "store.showing": "แสดง",
    "store.products": "สินค้า",
    "store.sortPopular": "ยอดนิยม",
    "store.sortNewest": "ใหม่ล่าสุด",
    "store.sortPriceLow": "ราคา: ต่ำ → สูง",
    "store.sortPriceHigh": "ราคา: สูง → ต่ำ",
    "store.sortRating": "คะแนนสูงสุด",
    "store.trust1": "รับประกันคืนเงิน 30 วัน",
    "store.trust2": "ส่งมอบดิจิทัลทันที",
    "store.trust3": "อัปเดตฟรีตลอดชีพ",
    "store.allProducts": "สินค้าทั้งหมด",

    // Product Page
    "product.backToStore": "กลับไปร้านค้า",
    "product.buyNow": "ซื้อเลย",
    "product.premiumAccess": "การเข้าถึงระดับพรีเมียม",
    "product.oneTime": "จ่ายครั้งเดียว · ส่งมอบทันที",
    "product.whatsIncluded": "มีอะไรบ้าง",
    "product.customersSay": "ลูกค้าพูดว่าอะไร",
    "product.youllReceive": "สิ่งที่คุณจะได้รับ",
    "product.faqTitle": "คำถามที่พบบ่อย",
    "product.readyToStart": "พร้อมเริ่มต้นหรือยัง?",
    "product.joinCustomers": "ลูกค้าที่กำลังใช้สินค้านี้อยู่",
    "product.getInstantAccess": "เข้าถึงทันที",
    "product.instantAccess": "เข้าถึงทันทีหลังชำระเงิน",
    "product.stripeEncrypted": "เข้ารหัส Stripe 256 บิต",
    "product.moneyBack": "รับประกันคืนเงิน",
    "product.happyCustomers": "ลูกค้าที่พอใจ",
    "product.secureEncrypted": "ชำระเงินปลอดภัย เข้ารหัส",
    "product.limitedOffer": "ข้อเสนอจำกัดเวลาสิ้นสุดใน:",
    "product.freeSample": "ทดลองใช้ฟรีก่อน",
    "product.freeSampleDesc": "ดูคุณภาพก่อนตัดสินใจซื้อ",
    "product.getFreeSample": "รับตัวอย่างฟรี",
    "product.deliveryEmail": "อีเมลสำหรับรับสินค้า",
    "product.unlockAccess": "ปลดล็อกการเข้าถึงตอนนี้",
    "product.connecting": "กำลังเชื่อมต่อ Stripe...",
    "product.notFound": "ไม่พบสินค้า",
    "product.notFoundDesc": "สินค้าที่คุณค้นหาไม่มีอยู่ในระบบ",
    "product.browseStore": "ดูร้านค้า",

    // Language
    "lang.switch": "EN",
  },
};

export function t(locale: Locale, key: string, params?: Record<string, string | number>): string {
  let text = translations[locale]?.[key] || translations.en[key] || key;
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      text = text.replace(`{${k}}`, String(v));
    });
  }
  return text;
}

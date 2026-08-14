import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from "react";
import { translations, type Locale } from "./translations";
import { preloadThaiProducts } from "../data/products";

interface LanguageContextType {
  locale: Locale;
  toggle: () => void;
  t: (key: string, params?: Record<string, string | number>) => string;
}

const LanguageContext = createContext<LanguageContextType | null>(null);

function getInitialLocale(): Locale {
  try {
    const saved = localStorage.getItem("ai-factory-lang");
    if (saved === "th" || saved === "en") return saved;
  } catch {}
  return "en";
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [locale, setLocale] = useState<Locale>(getInitialLocale);

  // Eagerly preload Thai product data when locale is TH
  useEffect(() => {
    if (locale === "th") preloadThaiProducts();
  }, [locale]);

  // Sync <html lang> + localized document title (audit: i18n #4)
  useEffect(() => {
    document.documentElement.lang = locale;
    // RTL-ready: set dir for future RTL locales (e.g. 'ar'); th/en are LTR
    document.documentElement.dir = (locale as string) === "ar" ? "rtl" : "ltr";
    document.title = locale === "th" ? "Ai Factory — ร้านเครื่องมือ AI สำหรับคนไทย" : "Ai Factory — AI Tools for Thai Creators";
  }, [locale]);

  const toggle = useCallback(() => {
    setLocale((prev) => {
      const next = prev === "en" ? "th" : "en";
      try { localStorage.setItem("ai-factory-lang", next); } catch {}
      return next;
    });
  }, []);

  const t = useCallback(
    (key: string, params?: Record<string, string | number>) => {
      let text = translations[locale]?.[key] || translations.en[key] || key;
      if (params) {
        Object.entries(params).forEach(([k, v]) => {
          text = text.replace(new RegExp(`\\{${k}\\}`, "g"), String(v));
        });
      }
      return text;
    },
    [locale]
  );

  return (
    <LanguageContext.Provider value={{ locale, toggle, t }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLang() {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error("useLang must be used within LanguageProvider");
  return ctx;
}

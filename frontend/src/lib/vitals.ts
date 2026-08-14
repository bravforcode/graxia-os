/**
 * Core Web Vitals monitoring (audit: Performance Perception).
 * Budgets: LCP ≤ 2.5s · INP ≤ 200ms · CLS ≤ 0.1
 * Logs to console as a table; flips a flag on document.body when a metric
 * misses its budget so issues are visible in dev/screenshots.
 */
import { onCLS, onINP, onLCP } from "web-vitals";

const BUDGETS: Record<string, { threshold: number; unit: string }> = {
  LCP: { threshold: 2500, unit: "ms" },
  INP: { threshold: 200, unit: "ms" },
  CLS: { threshold: 0.1, unit: "" },
};

export function initWebVitals() {
  const report = (name: string, value: number) => {
    const budget = BUDGETS[name];
    const ok = budget ? value <= budget.threshold : true;
    const label = `${name}: ${budget ? value.toFixed(0) : value.toFixed(3)}${budget.unit} ${ok ? "✅" : "❌ over budget"}`;
    // eslint-disable-next-line no-console
    console.info(`[CWV] ${label}`);
    if (!ok) document.body.setAttribute("data-cwv-issue", name);
  };

  onLCP((m) => report("LCP", m.value), { reportAllChanges: true });
  onINP((m) => report("INP", m.value), { reportAllChanges: true });
  onCLS((m) => report("CLS", m.value), { reportAllChanges: true });
}

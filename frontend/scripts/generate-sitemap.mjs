import { readFile, writeFile } from "node:fs/promises";

const root = new URL("../", import.meta.url);
const source = await readFile(new URL("src/data/products.ts", root), "utf8");
const slugs = [...source.matchAll(/slug:\s*"([^"]+)"/g)].map((match) => match[1]);
const staticPaths = [
  "/", "/store", "/revenue-os", "/privacy", "/terms", "/refund", "/delivery",
  "/guides/ai-prompt-workflows",
  "/guides/freelance-pricing-systems",
  "/guides/sme-automation-systems",
  "/free/prompt-pack-lite",
  "/free/freelance-pricing-calculator-lite",
  "/free/n8n-sme-automation-checklist",
];
const urls = [...staticPaths, ...slugs.map((slug) => `/store/${slug}`)];
const siteUrl = (process.env.VITE_SITE_URL || "https://bravforcode.github.io/graxia").replace(/\/+$/, "");
const body = urls.map((path) => `  <url><loc>${siteUrl}${path}</loc><changefreq>${path === "/" || path === "/store" ? "daily" : "weekly"}</changefreq><priority>${path === "/" ? "1.0" : path === "/store" ? "0.9" : "0.8"}</priority></url>`).join("\n");
await writeFile(new URL("public/sitemap.xml", root), `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${body}\n</urlset>\n`);

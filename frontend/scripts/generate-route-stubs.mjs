import { copyFile, mkdir, readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = dirname(fileURLToPath(import.meta.url));
const projectRoot = join(frontendRoot, "..");
const distRoot = join(projectRoot, "dist");
const indexPath = join(distRoot, "index.html");
const productSource = await readFile(join(projectRoot, "src/data/products.ts"), "utf8");
const magnetSource = await readFile(join(projectRoot, "src/data/organic.ts"), "utf8");
const products = [...productSource.matchAll(/slug:\s*"([^"]+)"/g)].map((match) => match[1]);
const magnets = [...magnetSource.matchAll(/slug:\s*"([^"]+)"/g)].map((match) => match[1]);

const routes = new Set([
  "store",
  "revenue-os",
  "privacy",
  "terms",
  "refund",
  "delivery",
  "checkout/success",
  "guides/ai-prompt-workflows",
  "guides/freelance-pricing-systems",
  "guides/sme-automation-systems",
  ...products.map((slug) => `store/${slug}`),
  ...magnets.map((slug) => `free/${slug}`),
]);

for (const route of routes) {
  const target = join(distRoot, route, "index.html");
  await mkdir(dirname(target), { recursive: true });
  await copyFile(indexPath, target);
}

await copyFile(indexPath, join(distRoot, "404.html"));

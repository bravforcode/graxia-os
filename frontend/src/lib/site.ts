const configuredSiteUrl = (import.meta.env.VITE_SITE_URL || "https://bravforcode.github.io/graxia").trim();

export const SITE_URL = configuredSiteUrl.replace(/\/+$/, "");

export function siteUrl(path = ""): string {
  const normalizedPath = path ? `/${path.replace(/^\/+/, "")}` : "";
  return `${SITE_URL}${normalizedPath}`;
}

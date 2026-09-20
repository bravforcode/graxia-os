export type AttributionTouch = {
  source?: string;
  medium?: string;
  campaign?: string;
  referrer?: string;
  path: string;
  referral_code?: string;
};

export type AttributionContext = {
  session_id: string;
  first_touch?: AttributionTouch;
  last_touch?: AttributionTouch;
  landing_path: string;
  content_id?: string;
  referral_code?: string;
};

const ATTRIBUTION_KEY = "graxia_attribution_v1";
const SESSION_KEY = "graxia_session_id_v1";
const MAX = 160;
const EVENT_METADATA_KEYS = new Set([
  "content_id",
  "cta",
  "path",
  "plan",
  "channel",
  "locale",
  "landing_path",
  "referral_code",
]);

function clip(value: string | null | undefined): string | undefined {
  const normalized = value?.trim();
  return normalized ? normalized.slice(0, MAX) : undefined;
}

function safeReferrer(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value, window.location.origin);
    return clip(`${url.origin}${url.pathname}`);
  } catch {
    return undefined;
  }
}

function sessionId(): string {
  const existing = sessionStorage.getItem(SESSION_KEY);
  if (existing) return existing;
  const generated = globalThis.crypto?.randomUUID?.() ?? `s-${Date.now()}-${Math.random()}`;
  sessionStorage.setItem(SESSION_KEY, generated);
  return generated;
}

function readContext(): AttributionContext | null {
  const raw = localStorage.getItem(ATTRIBUTION_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AttributionContext;
  } catch {
    localStorage.removeItem(ATTRIBUTION_KEY);
    return null;
  }
}

function touchFromUrl(rawUrl: string): AttributionTouch {
  const url = new URL(rawUrl, window.location.origin);
  const touch: AttributionTouch = {
    source: clip(url.searchParams.get("utm_source")),
    medium: clip(url.searchParams.get("utm_medium")),
    campaign: clip(url.searchParams.get("utm_campaign")),
    referrer: safeReferrer(document.referrer),
    path: clip(url.pathname) ?? "/",
    referral_code: clip(
      url.searchParams.get("referral_code") ?? url.searchParams.get("ref"),
    ),
  };
  return touch;
}

export function captureAttribution(rawUrl = window.location.href): AttributionContext {
  const previous = readContext();
  const touch = touchFromUrl(rawUrl);
  const next: AttributionContext = {
    session_id: previous?.session_id ?? sessionId(),
    first_touch: previous?.first_touch ?? touch,
    last_touch: touch,
    landing_path: previous?.landing_path ?? touch.path,
    referral_code: previous?.referral_code ?? touch.referral_code,
  };
  localStorage.setItem(ATTRIBUTION_KEY, JSON.stringify(next));
  return next;
}

export function getAttribution(): AttributionContext {
  return readContext() ?? captureAttribution();
}

export function getAttributionEventFields(
  metadata: Record<string, unknown> = {},
) {
  const attribution = getAttribution();
  const touch = attribution.last_touch ?? attribution.first_touch;
  const safeMetadata = Object.fromEntries(
    Object.entries(metadata)
      .filter(([key, value]) => EVENT_METADATA_KEYS.has(key) && value != null)
      .map(([key, value]) => [key, String(value).slice(0, MAX)]),
  );
  return {
    session_id: attribution.session_id,
    source: touch?.source,
    medium: touch?.medium,
    campaign: touch?.campaign,
    referrer: touch?.referrer,
    first_touch: attribution.first_touch,
    last_touch: attribution.last_touch,
    landing_path: attribution.landing_path,
    referral_code: attribution.referral_code,
    content_id: safeMetadata.content_id ?? attribution.content_id,
    metadata_json: safeMetadata,
  };
}
